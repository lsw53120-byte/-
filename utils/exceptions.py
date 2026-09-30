class LoginRequiredError(Exception):
    pass


class SearchConsoleTimeout(Exception):
    pass


class BrowserConnectionError(Exception):
    pass


class IndexRequestError(Exception):
    pass


class NetworkError(Exception):
    pass


class InvalidUrlError(Exception):
    pass
