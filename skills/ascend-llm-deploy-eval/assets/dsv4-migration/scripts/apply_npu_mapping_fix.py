from pathlib import Path
import shutil, sys, datetime
import argparse
parser=argparse.ArgumentParser()
parser.add_argument("--source", required=True)
parser.add_argument("--backup-dir", required=True)
parser.add_argument("--check", action="store_true")
args=parser.parse_args()
p = Path(args.source)
old = '''        elif current_platform.is_out_of_tree():
            self.device = torch.device(
                f"{current_platform.device_name}:{self.device_index}"
            )'''
new = '''        elif current_platform.is_out_of_tree():
            visible_device_index = current_platform.logical_device_id_to_visible_device_id(
                self.device_index
            )
            self.device = torch.device(
                f"{current_platform.device_name}:{visible_device_index}"
            )'''
s = p.read_text()
if new in s:
    print("Already applied")
elif s.count(old) == 1:
    if "--check" in sys.argv:
        raise SystemExit("Mapping patch is missing")
    result = s.replace(old, new)
    compile(result, str(p), "exec")
    backup = Path(args.backup_dir) / ("parallel_state.py." + datetime.datetime.now().strftime("%Y%m%d%H%M%S"))
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(p, backup)
    p.write_text(result)
    print("Applied:", p, "Backup:", backup)
else:
    raise SystemExit("Source version mismatch; no files changed")