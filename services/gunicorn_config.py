
import multiprocessing

workers = 4
threads = multiprocessing.cpu_count() * 2 + 1
max_requests = 1000
