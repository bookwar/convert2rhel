__metaclass__ = type

import hashlib
import os
import shutil

import pytest
import six

from convert2rhel import exceptions
from convert2rhel.backup import files
from convert2rhel.backup.files import MissingFile, RestorableFile


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


class TestRestorableFile:
    @pytest.fixture
    def get_backup_file_dir(self, tmpdir, filename="filename", content="content", backup_dir_name="backup"):
        """Prepare the file for backup and backup folder"""
        file_for_backup = tmpdir.join(filename)
        file_for_backup.write(content)
        backup_dir = tmpdir.mkdir(backup_dir_name)
        return file_for_backup, backup_dir

    @pytest.mark.parametrize(
        ("filepath", "isdir", "exception", "match"),
        (
            (
                "test.txt",
                False,
                TypeError,
                "Filepath needs to be an absolute path.",
            ),
            ("/test", True, TypeError, "Path must be a file not a directory."),
        ),
    )
    def test_restorable_file_type_error(self, filepath, isdir, exception, match, monkeypatch):
        monkeypatch.setattr(os.path, "isdir", lambda path: isdir)
        with pytest.raises(exception, match=match):
            RestorableFile(filepath)

    @pytest.mark.parametrize(
        ("filename", "message_backup", "message_remove", "message_restore", "backup_exists"),
        (
            (
                "filename",
                "Copied {file_for_backup} to {backedup_file}.",
                "File {file_for_backup} removed.",
                "File {file_for_backup} restored.",
                True,
            ),
            (
                None,
                "Can't find {file_for_backup}.",
                "Couldn't remove restored file {file_for_backup}",
                "{file_for_backup} hasn't been backed up.",
                False,
            ),
        ),
    )
    def test_restorable_file_all(
        self,
        caplog,
        filename,
        get_backup_file_dir,
        monkeypatch,
        message_backup,
        message_remove,
        message_restore,
        backup_exists,
        global_backup_control,
    ):
        """Test the complete process of backup and restore the file using the BackupController.
        Can be used as an example how to work with BackupController"""
        # Prepare file and folder for backup
        file_for_backup, backup_dir = get_backup_file_dir
        backup_dir = str(backup_dir)
        file_for_backup = str(file_for_backup)

        if filename:
            # location, where the file should be after backup
            dirname = os.path.dirname(backup_dir)
            backedup_file = os.path.join(backup_dir, hashlib.md5(dirname.encode()).hexdigest(), filename)
        else:
            file_for_backup = "/invalid/path/invalid_name"
            backedup_file = os.path.join(str(backup_dir), "invalid_name")

        # Format the messages which should be in output
        message_backup = message_backup.format(file_for_backup=file_for_backup, backedup_file=backedup_file)
        message_restore = message_restore.format(file_for_backup=file_for_backup)
        message_remove = message_remove.format(file_for_backup=file_for_backup)

        monkeypatch.setattr(files, "BACKUP_DIR", backup_dir)

        file_backup = RestorableFile(str(file_for_backup))

        # Create the backup, testing method enable
        global_backup_control.push(file_backup)
        assert message_backup in caplog.records[-1].message
        assert os.path.isfile(backedup_file) == backup_exists

        # Remove the file from original place, testing method remove
        file_backup.remove()
        assert message_remove in caplog.records[-1].message
        assert os.path.isfile(backedup_file) == backup_exists
        if filename:
            assert not os.path.isfile(file_for_backup)

        # Restore the file
        global_backup_control.pop()
        assert message_restore in caplog.records[-1].message
        if filename:
            assert os.path.isfile(file_for_backup)

    @pytest.mark.parametrize(
        ("filename", "enabled_preset", "enabled_value", "message", "backed_up"),
        (
            ("filename", False, True, "Copied {file_for_backup} to {backedup_file}.", True),
            (None, False, False, "Can't find {file_for_backup}.", False),
            ("filename", True, True, "", False),
        ),
    )
    def test_restorable_file_enable(
        self,
        filename,
        get_backup_file_dir,
        monkeypatch,
        enabled_preset,
        enabled_value,
        message,
        caplog,
        backed_up,
    ):
        # Prepare file and folder for backup
        file_for_backup, backup_dir = get_backup_file_dir
        backup_dir = str(backup_dir)

        # Prepare path where the file should be backed up
        if filename:
            dirname = os.path.dirname(backup_dir)
            backedup_file = os.path.join(backup_dir, hashlib.md5(dirname.encode()).hexdigest(), filename)
        else:
            file_for_backup = "/invalid/path/invalid_name"
            backedup_file = os.path.join(backup_dir, "invalid_name")

        file_for_backup = str(file_for_backup)

        # Prepare message
        message = message.format(file_for_backup=file_for_backup, backedup_file=backedup_file)

        monkeypatch.setattr(files, "BACKUP_DIR", backup_dir)
        file_backup = RestorableFile(file_for_backup)

        # Set the enabled value if needed, default is False
        file_backup.enabled = enabled_preset

        # Run the backup
        file_backup.enable()

        assert os.path.isfile(backedup_file) == backed_up
        assert file_backup.enabled == enabled_value
        if message:
            assert message in caplog.records[-1].message
        else:
            assert not caplog.records

    @pytest.mark.parametrize(
        ("filename", "messages", "enabled", "rollback", "isfile"),
        (
            (
                "filename",
                ["Rollback: Restore {orig_path} from backup", "File {orig_path} restored."],
                True,
                True,
                True,
            ),
            (
                None,
                ["Rollback: Restore {orig_path} from backup", "{orig_path} hasn't been backed up."],
                True,
                True,
                False,
            ),
            (
                "filename",
                ["Rollback: Restore {orig_path} from backup", "{orig_path} hasn't been backed up."],
                False,
                True,
                False,
            ),
            ("filename", ["Restoring {orig_path} from backup", "File {orig_path} restored."], True, False, True),
        ),
    )
    def test_restorable_file_restore(self, tmpdir, monkeypatch, caplog, filename, messages, enabled, rollback, isfile):
        backup_dir = tmpdir.mkdir("backup")
        backup_file = backup_dir.join("test")
        backup_file.write("content")
        backup_file = str(backup_file)

        if filename:
            file_for_restore = tmpdir.join("backup/filename")
            file_for_restore.write("content")

        for i, _ in enumerate(messages):
            messages[i] = messages[i].format(orig_path=backup_file)

        monkeypatch.setattr(os.path, "isfile", lambda file: isfile)
        monkeypatch.setattr(shutil, "copy2", mock.Mock())
        monkeypatch.setattr(files, "BACKUP_DIR", str(backup_dir))

        file_backup = RestorableFile(backup_file)
        file_backup.enabled = enabled
        file_backup.restore(rollback=rollback)

        for i, message in enumerate(messages):
            assert message in caplog.records[i].message

        if filename and enabled:
            assert os.path.isfile(backup_file)

    def test_restorable_file_backup_oserror(self, tmpdir, caplog, monkeypatch):
        backup_dir = tmpdir.mkdir("backup")
        backup_file = backup_dir.join("filename")
        backup_file.write("content")

        monkeypatch.setattr(
            shutil,
            "copy2",
            mock.Mock(side_effect=[None, OSError(2, "No such file or directory")]),
        )
        monkeypatch.setattr(os.path, "isfile", lambda file: True)
        monkeypatch.setattr(files, "BACKUP_DIR", str(backup_dir))
        file_backup = RestorableFile(str(backup_file))
        file_backup.enable()
        file_backup.restore()

        assert "Error(2): No such file or directory" in caplog.records[-1].message

    @pytest.mark.parametrize(
        ("file", "filepath", "message"),
        (
            (False, "/invalid/path", "Couldn't remove restored file /invalid/path"),
            (True, "filename", "File %s removed."),
        ),
    )
    def test_restorable_file_remove(self, tmpdir, caplog, file, filepath, message):
        if file:
            path = tmpdir.join(filepath)
            path.write("content")
            path = str(path)
            message = message % path
        else:
            path = filepath

        restorable_file = RestorableFile(path)
        restorable_file.remove()

        assert message in caplog.text

    def test_restorable_file_backup_critical_error(self, tmpdir, caplog, global_backup_control):
        tmp_file = tmpdir.join("test.rpm")
        tmp_file.write("test")
        rf = RestorableFile(filepath=str(tmp_file))

        with pytest.raises(exceptions.CriticalError):
            global_backup_control.push(rf)

        assert "Error(13): Permission denied" in caplog.records[-1].message

    @pytest.mark.parametrize(
        ("filepath",),
        (
            ("/test.txt",),
            ("/another/directory/file.txt",),
        ),
    )
    def test_hash_backup_path(self, filepath, tmpdir, monkeypatch):
        backup_dir = str(tmpdir)
        monkeypatch.setattr(files, "BACKUP_DIR", backup_dir)
        path, name = os.path.split(filepath)
        expected = "%s/%s/%s" % (backup_dir, hashlib.md5(path.encode()).hexdigest(), name)
        file = RestorableFile(filepath)

        result = file._hash_backup_path()
        assert os.path.exists(os.path.dirname(result))
        assert result == expected


class TestMissingFile:
    @pytest.mark.parametrize(
        ("exists", "expected", "message"),
        (
            (True, False, "The file {filepath} is present on the system before conversion, skipping it."),
            (False, True, "Marking file {filepath} as missing on system."),
        ),
    )
    def test_created_file_enable(self, exists, expected, tmpdir, caplog, message):
        path = tmpdir.join("filename")

        if exists:
            path.write("content")

        created_file = MissingFile(str(path))
        created_file.enable()

        assert created_file.enabled == expected
        assert message.format(filepath=str(path)) == caplog.records[-1].message

    @pytest.mark.parametrize(
        ("exists", "enabled", "message"),
        (
            (True, True, "File {filepath} removed"),
            (True, False, None),
            (False, True, "File {filepath} wasn't created during conversion"),
        ),
    )
    def test_created_file_restore(self, tmpdir, exists, enabled, message, caplog):
        path = tmpdir.join("filename")

        if exists:
            path.write("content")

        created_file = MissingFile(str(path))
        created_file.enabled = enabled
        created_file.restore()

        if enabled and exists:
            assert not exists == os.path.isfile(str(path))
        else:
            assert exists == os.path.isfile(str(path))

        if enabled:
            assert message.format(filepath=str(path)) == caplog.records[-1].message
        else:
            assert not caplog.records

    def test_created_file_restore_oserror(self, monkeypatch, tmpdir, caplog):
        path = tmpdir.join("filename")
        path.write("content")

        remove = mock.Mock(side_effect=OSError(2, "No such file or directory"))
        monkeypatch.setattr(os, "remove", remove)

        created_file = MissingFile(str(path))
        created_file.enabled = True
        created_file.restore()

        assert "Error(2): No such file or directory" in caplog.records[-1].message

    @pytest.mark.parametrize(
        ("exists", "created", "message_push", "message_pop"),
        (
            (False, True, "Marking file {filepath} as missing on system.", "File {filepath} removed"),
            (True, False, "The file {filepath} is present on the system before conversion, skipping it.", None),
            (
                False,
                False,
                "Marking file {filepath} as missing on system.",
                "File {filepath} wasn't created during conversion",
            ),
        ),
    )
    def test_created_file_all(self, tmpdir, exists, message_push, message_pop, caplog, created, global_backup_control):
        path = tmpdir.join("filename")

        if exists:
            # exists before conversion
            path.write("content")

        created_file = MissingFile(str(path))
        global_backup_control.push(created_file)

        assert message_push.format(filepath=str(path)) == caplog.records[-1].message

        if created:
            # created during conversion the file
            path.write("content")

        global_backup_control.pop()

        if message_pop:
            assert message_pop.format(filepath=str(path)) == caplog.records[-1].message
        if exists:
            assert os.path.isfile(str(path))
        else:
            assert not os.path.isfile(str(path))

    def test_enable_with_file_enabled(self, monkeypatch, caplog):
        """Verify that we are not enabling the same file twice."""
        monkeypatch.setattr(os.path, "isfile", lambda file: False)
        missing_file = MissingFile("/file.txt")
        missing_file.enable()

        assert missing_file.enabled
        assert "Marking file /file.txt as missing on system." in caplog.records[-1].message

        missing_file.enable()
        assert missing_file.enabled
        # Comparing the length of the records with 1 means that we exited
        # earlier in the `enable()` function. Not the strongest comparision,
        # but this should do.
        assert len(caplog.records) == 1

    def test_restore_with_file_enabled(self, monkeypatch, caplog):
        """Test that we are not restoring the same file twice"""
        monkeypatch.setattr(os.path, "isfile", lambda file: True)

        monkeypatch.setattr(os, "remove", lambda file: None)
        missing_file = MissingFile("/file.txt")
        missing_file.enabled = True

        missing_file.restore()
        assert "File /file.txt removed" in caplog.records[-1].message

        missing_file.restore()
        # Comparing the length of the records with 2 means that we exited
        # earlier in the `enable()` function. Not the strongest comparision,
        # but this should do.
        assert len(caplog.records) == 2
