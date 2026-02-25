class TokenException(Exception): #use to kill thread
    pass

class GithubFetchException(Exception): #use when something connection related fails to retry with other thread sometime later
    pass