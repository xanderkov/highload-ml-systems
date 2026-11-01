import json
from app import cache_info


def test_mac_groups():
    values = {'hw.perflevel0.name': 'Performance', 'hw.perflevel0.l1dcachesize': '131072',
              'hw.perflevel0.l2cachesize': '16777216', 'hw.perflevel1.name': 'Efficiency',
              'hw.perflevel1.l1dcachesize': '65536'}
    entries = cache_info.mac_entries(lambda key: values.get(key, ''))
    assert [(e['group'], e['level'], e['bytes']) for e in entries] == [
        ('Performance', 1, 131072), ('Performance', 2, 16777216), ('Efficiency', 1, 65536)]


def test_host_fallback(tmp_path, monkeypatch):
    native = {'model': '', 'architecture': 'aarch64', 'entries': []}
    monkeypatch.setattr(cache_info, 'collect', lambda: native)
    report = tmp_path / 'host.json'
    monkeypatch.setenv('HOST_CACHE_INFO', str(report))
    assert cache_info.get_cache_info() == native
    host = {'model': 'Apple M4 Pro', 'architecture': 'arm64', 'source': 'sysctl', 'entries': []}
    report.write_text(json.dumps(host))
    assert cache_info.get_cache_info()['model'] == 'Apple M4 Pro'
    host['architecture'] = 'x86_64'
    report.write_text(json.dumps(host))
    assert cache_info.get_cache_info() == native


def test_linux_cache_sizes(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_info.os, 'sched_getaffinity', lambda _: {0})
    for cpu in [0, 1]:
        index = tmp_path / f'cpu{cpu}/cache/index0'
        index.mkdir(parents=True)
        for name, value in {'level': '1', 'type': 'Data', 'size': '32K'}.items():
            (index / name).write_text(value)
    assert cache_info.linux_entries(tmp_path) == [{'level': 1, 'type': 'Data', 'bytes': 32768, 'group': 'CPU'}]
