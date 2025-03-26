def get_tokens():
    tokens = []
    with open('GitHubTokens', 'r') as file:
        for line in file:
            tokens.append(line.strip())
    return tokens