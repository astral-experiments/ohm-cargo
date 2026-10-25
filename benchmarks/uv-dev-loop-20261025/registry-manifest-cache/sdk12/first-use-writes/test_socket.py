from pathlib import Path
import importlib.util


def checks():
    path = Path(__file__).with_name('decode_writes.py')
    spec = importlib.util.spec_from_file_location('tested_write_decoder', path)
    decoder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(decoder)
    result = []
    for text in ('726<UNIX:[350161->350160]>', '1<UNIX:[0->0]>', '123<UNIX:[999999999->123456]>'):
        assert decoder.split_arguments(text) == [text]
        row, = decoder.records('close(' + text + ') = 0\n')
        assert row['args'] == [text] and row['kind'] == 'close'
        result.append({'case': text, 'passed': True})
    for text in ('726<UNIX:[350161->]>', '726<UNIX:[->350160]>', '726<UNIX:[350161->350160]]>',
                 '726<UNIX:[350161->350160>', '726<UNKNOWN:[350161->350160]>', '726<UNIX:[350161->350160]>junk>'):
        try:
            decoder.split_arguments(text)
        except AssertionError:
            result.append({'case': text, 'refused': True})
        else:
            raise AssertionError(text)
    assert decoder.split_arguments('1</tmp/file>, "<UNIX:[1->2]>", 13') == ['1</tmp/file>', '"<UNIX:[1->2]>"', '13']
    result.append({'case': 'quoted-arrow-payload-preserved', 'passed': True})
    return result
