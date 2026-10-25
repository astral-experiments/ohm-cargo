"""Worker-local orphan ownership; no bank may move until this guard passes."""
import ctypes
import os
from pathlib import Path
import signal
import time


class OwnershipError(RuntimeError):
    pass


def process_stat(pid):
    text = Path(f'/proc/{pid}/stat').read_text()
    prefix, separator, tail = text.rpartition(') ')
    if not separator or not prefix.startswith(str(pid) + ' ('):
        raise OwnershipError('malformed process identity')
    fields = tail.split()
    if len(fields) < 20:
        raise OwnershipError('short process identity')
    return {'pid': pid, 'comm': prefix[len(str(pid))+2:], 'state': fields[0],
            'ppid': int(fields[1]), 'pgid': int(fields[2]), 'sid': int(fields[3]),
            'start_ticks': int(fields[19])}


def group_absent(pgid):
    if type(pgid) is not int or pgid <= 1 or pgid == os.getpgrp():
        raise OwnershipError('invalid owned group')
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return True
    return False


class Descendants:
    def __init__(self, save_record):
        self.pid = os.getpid()
        self.save_record = save_record
        self.sequence = 0
        self.groups = set()
        self.enabled = False
        self.libc = ctypes.CDLL(None, use_errno=True)
        if not hasattr(os, 'pidfd_open') or not hasattr(signal, 'pidfd_send_signal'):
            raise OwnershipError('pidfd support required')
        if len(list(Path('/proc/self/task').iterdir())) != 1:
            raise OwnershipError('single-threaded owner required')
        if signal.getsignal(signal.SIGCHLD) != signal.SIG_DFL:
            raise OwnershipError('default SIGCHLD disposition required')
        previous = self._get_subreaper()
        if previous != 0:
            raise OwnershipError('pre-existing subreaper ownership is unsupported')
        self.assert_no_children()
        fd = os.pidfd_open(self.pid, 0)
        try:
            signal.pidfd_send_signal(fd, 0, None, 0)
        finally:
            os.close(fd)
        self._prctl(36, ctypes.c_ulong(1))  # PR_SET_CHILD_SUBREAPER, this worker only.
        if self._get_subreaper() != 1:
            raise OwnershipError('subreaper enable did not take effect')
        self.enabled = True
        self._record('enabled', {'previous_subreaper': previous, 'worker_pid': self.pid})

    def _prctl(self, option, argument):
        if self.libc.prctl(ctypes.c_int(option), argument, ctypes.c_ulong(0),
                           ctypes.c_ulong(0), ctypes.c_ulong(0)) != 0:
            raise OSError(ctypes.get_errno(), 'worker-local prctl failed')

    def _get_subreaper(self):
        value = ctypes.c_int()
        self._prctl(37, ctypes.byref(value))  # PR_GET_CHILD_SUBREAPER.
        return value.value

    def _record(self, label, value):
        self.sequence += 1
        self.save_record(self.sequence, {'label': label, 'individual_times_retained': 0, **value})

    def children(self):
        if len(list(Path('/proc/self/task').iterdir())) != 1:
            raise OwnershipError('owner unexpectedly became multithreaded')
        pids = [int(x) for x in Path(f'/proc/self/task/{self.pid}/children').read_text().split()]
        if len(pids) != len(set(pids)):
            raise OwnershipError('duplicate owned child identity')
        rows = [process_stat(pid) for pid in pids]
        if any(row['ppid'] != self.pid or row['start_ticks'] <= 0 for row in rows):
            raise OwnershipError('child parent/start identity changed')
        return rows

    def assert_no_children(self):
        if self.children():
            raise OwnershipError('owned descendants remain')
        try:
            result = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            return
        raise OwnershipError('kernel child set was not empty: ' + repr(result))

    def _reap(self, rows, *, healthy):
        reaped = []
        for row in rows:
            pid, status = os.waitpid(row['pid'], os.WNOHANG)
            if pid:
                code = os.waitstatus_to_exitcode(status)
                reaped.append({**row, 'exitcode': code})
        if reaped:
            self._record('reaped-cleanup', {'children': reaped, 'healthy_exit_required': healthy})
        if healthy and any(row['exitcode'] != 0 for row in reaped):
            raise OwnershipError('owned cleanup exited unsuccessfully')
        return reaped

    def drain(self, label, *, group=None, seconds=5):
        if not self.enabled or self._get_subreaper() != 1:
            raise OwnershipError('subreaper ownership missing')
        if group is not None:
            group_absent(group)  # Validate the group identifier, without sending a signal.
            self.groups.add(group)
        observations = []
        deadline = time.monotonic() + seconds
        outcome = 'refused'
        try:
            while True:
                rows = self.children()
                observations.append(rows)
                if group is not None and any(row['pgid'] != group or row['sid'] != group for row in rows):
                    raise OwnershipError('owned descendant escaped the Cargo group/session')
                self._reap(rows, healthy=True)
                if not self.children():
                    self.assert_no_children()
                    if group is not None and not group_absent(group):
                        raise OwnershipError('group remains without an accountable owned child')
                    outcome = 'quiescent'
                    return
                if time.monotonic() >= deadline:
                    raise OwnershipError('owned cleanup did not drain within the fixed bound')
                time.sleep(0.025)
        finally:
            self._record(label, {'state': outcome, 'expected_group': group,
                                'observations': observations})

    def _owned_pidfds(self, rows):
        opened = []
        try:
            # Validate every target before sending the first signal. No pathname/PID guess is a target.
            for row in rows:
                if row['state'] in ('Z', 'X'):
                    continue
                fd = os.pidfd_open(row['pid'], 0)
                opened.append((row, fd))
                info = dict(line.split(':', 1) for line in Path(f'/proc/self/fdinfo/{fd}').read_text().splitlines()
                            if ':' in line)
                current = process_stat(row['pid'])
                if (int(info['Pid']) != row['pid'] or current['ppid'] != self.pid
                        or current['start_ticks'] != row['start_ticks']):
                    raise OwnershipError('pidfd target ownership is ambiguous')
            return opened
        except BaseException:
            for _, fd in opened:
                os.close(fd)
            raise

    def terminate_owned(self, label, *, seconds=10, primary=None):
        """Only used after a failed attempt; no next command or path reuse is allowed."""
        if not self.enabled or self._get_subreaper() != 1:
            raise OwnershipError('subreaper ownership missing during cleanup')
        observations = []
        signaled = []
        deadline = time.monotonic() + seconds
        outcome = 'blocked'
        try:
            while True:
                rows = self.children()
                observations.append(rows)
                opened = self._owned_pidfds(rows)
                try:
                    for row, fd in opened:
                        try:
                            signal.pidfd_send_signal(fd, signal.SIGKILL, None, 0)
                        except ProcessLookupError:
                            pass
                        signaled.append({'pid': row['pid'], 'start_ticks': row['start_ticks'],
                                         'parent_at_validation': self.pid, 'via_pidfd': True})
                finally:
                    for _, fd in opened:
                        os.close(fd)
                # Popen retains ownership of its own wait status; adopted orphans are ours.
                self._reap([row for row in rows if primary is None or row['pid'] != primary.pid], healthy=False)
                if primary is not None:
                    primary.poll()
                if not self.children():
                    self.assert_no_children()
                    if not all(group_absent(group) for group in self.groups):
                        raise OwnershipError('unaccounted process group remains after cleanup')
                    outcome = 'quiescent'
                    return
                if time.monotonic() >= deadline:
                    raise OwnershipError('owned cleanup remains blocked; preserve active roots')
                time.sleep(0.025)
        finally:
            self._record(label, {'state': outcome, 'observations': observations,
                                'terminated_owned_identities': signaled})

    def close(self):
        self.assert_no_children()
        if not all(group_absent(group) for group in self.groups):
            raise OwnershipError('cannot release worker ownership while a group remains')
        self._prctl(36, ctypes.c_ulong(0))
        if self._get_subreaper() != 0:
            raise OwnershipError('subreaper restore failed')
        self.enabled = False
        self._record('disabled', {'worker_pid': self.pid, 'restored_subreaper': 0})
