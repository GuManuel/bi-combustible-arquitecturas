import os,sys,time

def snapshot():
    # Lifetime high-water RSS on Unix. It is NOT a per-case incremental memory peak.
    try:
        import resource
        rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        mib=rss/(1024**2 if sys.platform=='darwin' else 1024)
    except ImportError:
        import psutil
        info=psutil.Process(os.getpid()).memory_info()
        mib=getattr(info,'peak_wset',info.rss)/2**20
    return {'cpu_seconds':time.process_time(),'lifetime_peak_rss_mib':mib}
