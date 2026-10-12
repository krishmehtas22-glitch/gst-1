import xml.etree.ElementTree as ET

from Common_Rules.engine import init_client, init_demo_client, read_json
from Common_Rules.watcher import DemoWatcher
from helpers import gstin
from test_demo import banner_pdf, banner_text


def settle(watcher):
    assert watcher.poll() is None
    return watcher.poll()


def test_new_client_same_invoice_independent_and_new_pdf(tmp_path):
    watcher = DemoWatcher(tmp_path)
    first = tmp_path / 'Client 1'
    first.mkdir()
    banner_pdf(first / 'one.pdf', banner_text())
    result = settle(watcher)
    assert result['clients'][0]['counts']['new'] == 1
    assert watcher.poll() is None
    second = tmp_path / 'Client 5'
    second.mkdir()
    banner_pdf(second / 'one.pdf', banner_text())
    result = settle(watcher)
    assert result['clients'][1]['counts']['new'] == 1
    configs = [read_json(p / 'client.json') for p in (first, second)]
    assert configs[0]['company_id'] != configs[1]['company_id']
    assert configs[1]['company_name'] == 'Client 5'
    assert len(ET.parse(second / 'imports/Sales_Vouchers.xml').findall('.//VOUCHER')) == 1
    assert watcher.poll() is None
    banner_pdf(second / 'two.pdf', banner_text(number='SAMPLE-002'))
    result = settle(watcher)
    assert result['clients'][1]['counts']['new'] == 1
    assert len(ET.parse(second / 'imports/Sales_Vouchers.xml').findall('.//VOUCHER')) == 2
    assert watcher.poll() is None


def test_preserves_mismatched_history_and_processes_other_clients(tmp_path):
    old = init_demo_client(tmp_path, 'Client 1', 'abc', 'Maharashtra', 'Nos')
    banner_pdf(old / 'one.pdf', banner_text())
    watcher = DemoWatcher(tmp_path)
    settle(watcher)
    config_path = old / 'client.json'
    original = config_path.read_text()
    config_path.unlink()
    new = tmp_path / 'Client 5'
    new.mkdir()
    banner_pdf(new / 'one.pdf', banner_text())
    result = settle(watcher)
    assert 'restore' in result['clients'][0]['error']
    assert not config_path.exists()
    assert result['clients'][1]['counts']['new'] == 1
    config_path.write_text(original)


def test_demo_launcher_does_not_process_real_clients(tmp_path):
    real = init_client(tmp_path, 'Real', 'Real Company', gstin())
    result = settle(DemoWatcher(tmp_path))
    assert 'real client' in result['error']
    assert not (real / 'imports').exists()


def test_one_hundred_clients_auto_configured_with_independent_xml(tmp_path):
    for n in range(1, 101):
        folder = tmp_path / f'Client {n}'
        folder.mkdir()
        banner_pdf(folder / 'invoice.pdf', banner_text())
    watcher = DemoWatcher(tmp_path)
    result = settle(watcher)
    assert len(result['clients']) == 100
    assert all(report['counts']['new'] == 1 for report in result['clients'])
    identities = set()
    for folder in tmp_path.iterdir():
        identities.add(read_json(folder / 'client.json')['company_id'])
        assert len(ET.parse(folder / 'imports/Sales_Vouchers.xml').findall('.//VOUCHER')) == 1
    assert len(identities) == 100
    assert watcher.poll() is None
