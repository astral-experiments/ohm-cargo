from pathlib import Path
import json
import os

class States:
    def __init__(self, active, banks, journal):
        assert set(active) == {'target', 'shared', 'package-home'}
        assert set(banks) == {'baseline', 'candidate'}
        self.active = {key: Path(value) for key, value in active.items()}
        self.banks = {arm: {key: Path(value) for key, value in rows.items()} for arm, rows in banks.items()}
        self.installed = {}
        self.journal = journal
        assert all(set(rows) == set(self.active) for rows in self.banks.values())
        paths = list(self.active.values()) + [p for rows in self.banks.values() for p in rows.values()]
        assert len(paths) == len(set(paths))
        assert all(p.is_absolute() for p in paths)
        assert not any(a in b.parents for a in paths for b in paths if a != b)
        assert all(not os.path.lexists(p) for p in self.active.values())
        assert all(p.is_dir() and not p.is_symlink() for rows in self.banks.values() for p in rows.values())

    def move(self, source, destination, arm, key):
        assert source.is_dir() and not source.is_symlink() and not os.path.lexists(destination)
        assert source.stat().st_dev == destination.parent.stat().st_dev
        before = source.stat()
        os.rename(source, destination)
        with self.journal.open('a') as stream:
            stream.write(json.dumps({'arm': arm, 'component': key, 'from': str(source), 'to': str(destination),
                                     'device': before.st_dev, 'inode': before.st_ino}) + '\n')
            stream.flush()
            os.fsync(stream.fileno())

    def park(self):
        for key, arm in list(self.installed.items()):
            if os.path.lexists(self.active[key]):
                self.move(self.active[key], self.banks[arm][key], arm, key)
            else:
                assert self.banks[arm][key].is_dir()
            del self.installed[key]

    def select(self, arm):
        self.park()
        for key in self.active:
            self.installed[key] = arm
            self.move(self.banks[arm][key], self.active[key], arm, key)
