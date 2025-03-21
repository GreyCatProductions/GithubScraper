import datetime


def log(level, message):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    levels = {
        "INFO": "\033[94m[INFO]\033[0m",
        "WARNING": "\033[93m[WARNING]\033[0m",
        "ERROR": "\033[91m[ERROR]\033[0m",
        "DEBUG": "\033[90m[DEBUG]\033[0m"
    }
    print(f"{timestamp} {levels[level]} {message}")
