class DeezerError(Exception):
    """Base class for Deezer exceptions"""

class WrongLicense(DeezerError):
    def __init__(self, track_format):
        super().__init__()
        self.message = f"Your account doesn't have the license to stream {track_format}"
        self.format = track_format

class WrongGeolocation(DeezerError):
    def __init__(self, country):
        super().__init__()
        self.message = f"The track you requested can't be streamed in country {country}"
        self.country = country

class APIError(DeezerError):
    """Base class for Deezer api exceptions"""

class ItemsLimitExceededException(APIError):
    pass

class PermissionException(APIError):
    pass

class InvalidTokenException(APIError):
    pass

class WrongParameterException(APIError):
    pass

class MissingParameterException(APIError):
    pass

class InvalidQueryException(APIError):
    pass

class DataException(APIError):
    pass

class IndividualAccountChangedNotAllowedException(APIError):
    pass

class GWAPIError(DeezerError):
    """Base class for Deezer gw api exceptions"""
