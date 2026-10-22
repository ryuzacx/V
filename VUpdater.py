import os, subprocess, sys, time
def main():
    if len(sys.argv)<5: return 2
    target, staged, old_pid, version=sys.argv[1:5]
    target=os.path.abspath(target); staged=os.path.abspath(staged); backup=target+".rollback"
    pid=int(old_pid)
    for _ in range(300):
        try: os.kill(pid,0); time.sleep(.1)
        except OSError: break
    else: return 3
    if not os.path.isfile(staged) or os.path.getsize(staged)<100000: return 4
    try:
        if os.path.exists(backup): os.remove(backup)
        os.replace(target,backup)
        try: os.replace(staged,target)
        except Exception: os.replace(backup,target); raise
        proc=subprocess.Popen([target],cwd=os.path.dirname(target))
        for _ in range(80):
            if proc.poll() is not None: raise RuntimeError("Updated V exited during startup.")
            time.sleep(.1)
        return 0
    except Exception:
        try:
            if os.path.exists(target): os.remove(target)
            if os.path.exists(backup):
                os.replace(backup,target); subprocess.Popen([target],cwd=os.path.dirname(target))
        except Exception: pass
        return 5
if __name__=="__main__": raise SystemExit(main())
