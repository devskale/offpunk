import shutil
import subprocess
from pathlib import Path
from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class TranslationFilesHook(BuildHookInterface):
    """Compile the GNU gettext translation files from their po-format into
    their binary representating mo-format using 'msgfmt'.
    """

    # Command used to compile po into mo files.
    COMPILE_COMMAND = 'msgfmt'

    def _check_compile_command(self):
        """Check if "msgfmt" is available."""

        if not shutil.which(type(self).COMPILE_COMMAND):
            raise OSError(
                'Executable "{cmd}" (from GNU gettext tools) is not '
                'available. Please install it via a package manager of '
                'your trust. In most cases "{cmd}" is part of "gettext".'
                .format(cmd=type(self).COMPILE_COMMAND)
            )

    def _compile_po_to_mo(self, po_file: Path, mo_file: Path):
        """ Compile po-file to mo-file using "msgfmt".
        """

        # Build command
        cmd = [
            type(self).COMPILE_COMMAND,
            '--output-file={}'.format(mo_file),
            po_file
        ]

        # Execute command
        rc = subprocess.run(cmd, check=False, text=True, capture_output=True)

        # Validate output
        if rc.stderr:
            raise RuntimeError(rc.stderr)

    def initialize(self, version, build_data):
        print('|==-- Preparing translation files. --==|')

        self._check_compile_command()

        pkg_path = Path.cwd()

        for in_file in pkg_path.glob('po/*.po'):
            print(f'Processing "{in_file.name}"')
            out_file = pkg_path / 'share/locale' / in_file.stem  / 'LC_MESSAGES' / 'offpunk.mo'
            # Create folder for output file
            out_file.parent.mkdir(parents=True, exist_ok=True)
            self._compile_po_to_mo(in_file, out_file)

        print('|==-- Completed. --==|')

