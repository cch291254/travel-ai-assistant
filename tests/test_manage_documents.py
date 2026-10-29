import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

from app import manage_documents as cli


@pytest.fixture
def resources(monkeypatch):
    collection = Mock()
    collection.name = 'test_collection'
    client = Mock()
    client.get_collection.return_value = collection
    persistent_client = Mock(return_value=client)
    conn = Mock()
    init_db = Mock(return_value=conn)
    model = Mock()
    validate=Mock()
    load_model = Mock(return_value=model)
    embedding = ModuleType('app.embedding')
    embedding.load_embedding_model = load_model
    index = Mock(return_value={'document_id': 'guide', 'written': 1, 'deleted': 0})
    delete = Mock(return_value={'document_id': 'guide', 'deleted_chunks': 1, 'deleted_registration': 1})
    path = Mock()
    path.is_dir.return_value = True
    path.is_file.return_value = True
    confirm = Mock(return_value='DELETE')

    monkeypatch.setattr(cli, 'Path', Mock(return_value=path))
    monkeypatch.setattr(cli.chromadb, 'PersistentClient', persistent_client)
    monkeypatch.setattr(cli, 'init_db', init_db)
    monkeypatch.setattr(cli, 'index_document_with_registration', index)
    monkeypatch.setattr(cli, 'delete_document_with_registration', delete)
    monkeypatch.setitem(sys.modules, 'app.embedding', embedding)
    monkeypatch.setattr('builtins.input', confirm)
    monkeypatch.setattr(cli, "validate_document_file", validate)

    def run(*args):
        monkeypatch.setattr(sys, 'argv', ['manage_documents.py', *args])
        return cli.main()

    return SimpleNamespace(
        collection=collection, client=client, persistent_client=persistent_client,
        conn=conn, init_db=init_db, model=model, load_model=load_model,
        index=index, delete=delete, path=path, confirm=confirm, run=run,validate=validate,  # 让具体测试可以设置校验失败
    )


def test_index_dispatch(resources, capsys):
    r = resources
    r.run('index', 'guide.md', '--collection', 'test_collection')
    r.persistent_client.assert_called_once_with(path='data/chroma')
    r.client.get_collection.assert_called_once_with(name='test_collection')
    r.client.get_or_create_collection.assert_not_called()
    r.init_db.assert_called_once_with('data/real_documents.db')
    r.load_model.assert_called_once_with()
    r.index.assert_called_once_with('guide.md', r.model, r.collection, r.conn)
    r.delete.assert_not_called()
    r.confirm.assert_not_called()
    r.conn.close.assert_called_once_with()
    assert 'written' in capsys.readouterr().out


def test_confirmed_delete_does_not_load_model(resources):
    r = resources
    r.run('delete', 'guide', '--collection', 'test_collection')
    r.confirm.assert_called_once()
    r.delete.assert_called_once_with('guide', r.collection, r.conn)
    r.index.assert_not_called()
    r.load_model.assert_not_called()
    r.conn.close.assert_called_once_with()


@pytest.mark.parametrize('answer', ['', 'delete', 'cancel'])
def test_cancelled_delete_opens_no_resources(resources, answer, capsys):
    r = resources
    r.confirm.return_value = answer
    r.run('delete', 'guide', '--collection', 'test_collection')
    r.persistent_client.assert_not_called()
    r.init_db.assert_not_called()
    r.load_model.assert_not_called()
    r.delete.assert_not_called()
    assert '已取消删除' in capsys.readouterr().out


@pytest.mark.parametrize('args, expected_code', [
    (['--help'], 0),
    (['index', 'guide.md'], 2),
    (['update', 'guide.md', '--collection', 'test_collection'], 2),
])
def test_argument_exit_precedes_resource_access(resources, args, expected_code):
    r = resources
    with pytest.raises(SystemExit) as error:
        r.run(*args)
    assert error.value.code == expected_code
    r.persistent_client.assert_not_called()
    r.init_db.assert_not_called()
    r.load_model.assert_not_called()


@pytest.mark.parametrize('missing', ['directory', 'file'])
def test_missing_paths_open_no_resources(resources, missing):
    r = resources
    if missing == 'directory':
        r.path.is_dir.return_value = False
    else:
        r.validate.side_effect = FileNotFoundError("资料文件不存在")
    with pytest.raises(SystemExit) as error:
        r.run('index', 'guide.md', '--collection', 'test_collection')
    assert error.value.code == 2
    r.persistent_client.assert_not_called()
    r.init_db.assert_not_called()
    r.load_model.assert_not_called()


def test_missing_collection_is_not_created(resources):
    r = resources
    r.client.get_collection.side_effect = RuntimeError('missing collection')
    with pytest.raises(RuntimeError, match='missing collection'):
        r.run('index', 'guide.md', '--collection', 'missing')
    r.client.get_or_create_collection.assert_not_called()
    r.init_db.assert_not_called()
    r.load_model.assert_not_called()


@pytest.mark.parametrize('action', ['index', 'delete'])
def test_operation_failure_closes_connection(resources, action):
    r = resources
    operation = r.index if action == 'index' else r.delete
    operation.side_effect = RuntimeError('operation failed')
    with pytest.raises(RuntimeError, match='operation failed'):
        r.run(action, 'guide', '--collection', 'test_collection')
    r.conn.close.assert_called_once_with()


def test_model_load_failure_closes_connection(resources):
    r = resources
    r.load_model.side_effect = RuntimeError('model unavailable')
    with pytest.raises(RuntimeError, match='model unavailable'):
        r.run('index', 'guide.md', '--collection', 'test_collection')
    r.index.assert_not_called()
    r.conn.close.assert_called_once_with()
