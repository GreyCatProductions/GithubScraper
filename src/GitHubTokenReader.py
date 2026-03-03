from pathlib import Path
from Logger import log

def get_tokens():
    tokens = []
    token_path = Path("../env/GithubTokens.txt").expanduser()
    try:
        with open(token_path, 'r', encoding='utf-8') as file:
            for line in file:
                if "#" in line:
                    continue
                tokens.append(line.strip())
    except Exception as e:
        log(-1, "ERROR", f"Failed to read tokens {e}")
    return tokens