cache="/home/ploum/.cache/offpunk/"
from pathlib import Path
import time

def dir_size(path):
    return sum(p.stat().st_size for p in Path(path).rglob("*") if p.is_file())

start = time.time()
total = dir_size(cache)
step1 = time.time()
print("size: %s Mb (in %s seconds)"%((int(total)/1000000,step1-start)))
files = [p for p in Path(cache).rglob("*") if p.is_file()]
step2 = time.time()
print("%s files (in %s seconds)"%((len(files),step2-step1)))
print("now sorting...")
files.sort(key=lambda p: p.stat().st_mtime)
step3 = time.time()
print("sorted in %s seconds"%(step3-step2))
