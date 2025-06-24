from Logger import log

def get_tokens():
    tokens = []
    try:
        with open('./keys/GitHubTokens', 'r', encoding='utf-8') as file:
            for line in file:
                if "#" in line:
                    continue
                tokens.append(line.strip())
    except Exception as e:
        log(-1, "ERROR", f"Failed to read tokens {e}")
    return tokens