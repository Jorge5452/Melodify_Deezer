import requests
from time import sleep

import json
from deezer.errors import ItemsLimitExceededException, PermissionException, InvalidTokenException, \
WrongParameterException, MissingParameterException, InvalidQueryException, DataException, \
IndividualAccountChangedNotAllowedException, APIError

class SearchOrder():
    """Possible values for order parameter in search"""
    RANKING       = "RANKING"
    TRACK_ASC     = "TRACK_ASC"
    TRACK_DESC    = "TRACK_DESC"
    ARTIST_ASC    = "ARTIST_ASC"
    ARTIST_DESC   = "ARTIST_DESC"
    ALBUM_ASC     = "ALBUM_ASC"
    ALBUM_DESC    = "ALBUM_DESC"
    RATING_ASC    = "RATING_ASC"
    RATING_DESC   = "RATING_DESC"
    DURATION_ASC  = "DURATION_ASC"
    DURATION_DESC = "DURATION_DESC"

class API:
    def __init__(self, session, headers):
        self.http_headers = headers
        self.session = session
        self.access_token = None

    def api_call(self, method, args=None):
        if args is None:
            args = {}
        if self.access_token: args['access_token'] = self.access_token
        try:
            result_json = self.session.get(
                "https://api.deezer.com/" + method,
                params=args,
                headers=self.http_headers,
                timeout=30
            ).json()
        except (requests.ConnectionError, requests.Timeout):
            sleep(2)
            return self.api_call(method, args)
        if 'error' in result_json.keys():
            if 'code' in result_json['error']:
                if result_json['error']['code'] in [4, 700]:
                    sleep(5)
                    return self.api_call(method, args)
                if result_json['error']['code'] == 100: raise ItemsLimitExceededException(f"ItemsLimitExceededException: {method} {result_json['error']['message'] if 'message' in result_json['error'] else ''}")
                if result_json['error']['code'] == 200: raise PermissionException(f"PermissionException: {method} {result_json['error']['message'] if 'message' in result_json['error'] else ''}")
                if result_json['error']['code'] == 300: raise InvalidTokenException(f"InvalidTokenException: {method} {result_json['error']['message'] if 'message' in result_json['error'] else ''}")
                if result_json['error']['code'] == 500: raise WrongParameterException(f"ParameterException: {method} {result_json['error']['message'] if 'message' in result_json['error'] else ''}")
                if result_json['error']['code'] == 501: raise MissingParameterException(f"MissingParameterException: {method} {result_json['error']['message'] if 'message' in result_json['error'] else ''}")
                if result_json['error']['code'] == 600: raise InvalidQueryException(f"InvalidQueryException: {method} {result_json['error']['message'] if 'message' in result_json['error'] else ''}")
                if result_json['error']['code'] == 800: raise DataException(f"DataException: {method} {result_json['error']['message'] if 'message' in result_json['error'] else ''}")
                if result_json['error']['code'] == 901: raise IndividualAccountChangedNotAllowedException(f"IndividualAccountChangedNotAllowedException: {method} {result_json['error']['message'] if 'message' in result_json['error'] else ''}")
            raise APIError(json.dumps(result_json['error']))
        return result_json

    def get_album(self, album_id):
        return self.api_call(f'album/{str(album_id)}')

    def get_album_by_UPC(self, upc):
        return self.get_album(f'upc:{upc}')

    def get_album_comments(self, album_id, index=0, limit=10):
        return self.api_call(f'album/{str(album_id)}/comments', {'index': index, 'limit': limit})

    def get_album_fans(self, album_id, index=0, limit=100):
        return self.api_call(f'album/{str(album_id)}/fans', {'index': index, 'limit': limit})

    def get_album_tracks(self, album_id, index=0, limit=-1):
        return self.api_call(f'album/{str(album_id)}/tracks', {'index': index, 'limit': limit})

    def get_artist(self, artist_id):
        return self.api_call(f'artist/{str(artist_id)}')

    def get_artist_top(self, artist_id, index=0, limit=10):
        return self.api_call(f'artist/{str(artist_id)}/top', {'index': index, 'limit': limit})

    def get_artist_albums(self, artist_id, index=0, limit=-1):
        return self.api_call(f'artist/{str(artist_id)}/albums', {'index': index, 'limit': limit})

    def get_artist_comments(self, artist_id, index=0, limit=10):
        return self.api_call(f'artist/{str(artist_id)}/comments', {'index': index, 'limit': limit})

    def get_artist_fans(self, artist_id, index=0, limit=100):
        return self.api_call(f'artist/{str(artist_id)}/fans', {'index': index, 'limit': limit})

    def get_artist_related(self, artist_id, index=0, limit=20):
        return self.api_call(f'artist/{str(artist_id)}/related', {'index': index, 'limit': limit})

    def get_artist_radio(self, artist_id, index=0, limit=25):
        return self.api_call(f'artist/{str(artist_id)}/radio', {'index': index, 'limit': limit})

    def get_artist_playlists(self, artist_id, index=0, limit=-1):
        return self.api_call(f'artist/{str(artist_id)}/playlists', {'index': index, 'limit': limit})

    def get_chart(self, genre_id=0, index=0, limit=10):
        return self.api_call(f'chart/{str(genre_id)}', {'index': index, 'limit': limit})

    def get_chart_tracks(self, genre_id=0, index=0, limit=10):
        return self.api_call(f'chart/{str(genre_id)}/tracks', {'index': index, 'limit': limit})

    def get_chart_albums(self, genre_id=0, index=0, limit=10):
        return self.api_call(f'chart/{str(genre_id)}/albums', {'index': index, 'limit': limit})

    def get_chart_artists(self, genre_id=0, index=0, limit=10):
        return self.api_call(f'chart/{str(genre_id)}/artists', {'index': index, 'limit': limit})

    def get_chart_playlists(self, genre_id=0, index=0, limit=10):
        return self.api_call(f'chart/{str(genre_id)}/playlists', {'index': index, 'limit': limit})

    def get_chart_podcasts(self, genre_id=0, index=0, limit=10):
        return self.api_call(f'chart/{str(genre_id)}/podcasts', {'index': index, 'limit': limit})

    def get_comment(self, comment_id):
        return self.api_call(f'comment/{str(comment_id)}')

    def get_editorials(self, index=0, limit=10):
        return self.api_call('editorial', {'index': index, 'limit': limit})

    def get_editorial(self, genre_id=0):
        return self.api_call(f'editorial/{str(genre_id)}')

    def get_editorial_selection(self, genre_id=0, index=0, limit=10):
        return self.api_call(f'editorial/{str(genre_id)}/selection', {'index': index, 'limit': limit})

    def get_editorial_charts(self, genre_id=0, index=0, limit=10):
        return self.api_call(f'editorial/{str(genre_id)}/charts', {'index': index, 'limit': limit})

    def get_editorial_releases(self, genre_id=0, index=0, limit=10):
        return self.api_call(f'editorial/{str(genre_id)}/releases', {'index': index, 'limit': limit})

    def get_genres(self, index=0, limit=10):
        return self.api_call('genre', {'index': index, 'limit': limit})

    def get_genre(self, genre_id=0):
        return self.api_call(f'genre/{str(genre_id)}')

    def get_genre_artists(self, genre_id=0, index=0, limit=10):
        return self.api_call(f'genre/{str(genre_id)}/artists', {'index': index, 'limit': limit})

    def get_genre_radios(self, genre_id=0, index=0, limit=10):
        return self.api_call(f'genre/{str(genre_id)}/radios', {'index': index, 'limit': limit})

    def get_infos(self):
        return self.api_call('infos')

    def get_options(self):
        return self.api_call('options')

    def get_playlist(self, playlist_id):
        return self.api_call(f'playlist/{str(playlist_id)}')

    def get_playlist_comments(self, album_id, index=0, limit=10):
        return self.api_call(f'playlist/{str(album_id)}/comments', {'index': index, 'limit': limit})

    def get_playlist_fans(self, album_id, index=0, limit=100):
        return self.api_call(f'playlist/{str(album_id)}/fans', {'index': index, 'limit': limit})

    def get_playlist_tracks(self, album_id, index=0, limit=-1):
        return self.api_call(f'playlist/{str(album_id)}/tracks', {'index': index, 'limit': limit})

    def get_playlist_radio(self, album_id, index=0, limit=100):
        return self.api_call(f'playlist/{str(album_id)}/radio', {'index': index, 'limit': limit})

    def get_radios(self, index=0, limit=10):
        return self.api_call('radio', {'index': index, 'limit': limit})

    def get_radios_genres(self, index=0, limit=25):
        return self.api_call('radio/genres', {'index': index, 'limit': limit})

    def get_radios_top(self, index=0, limit=50):
        return self.api_call('radio/top', {'index': index, 'limit': limit})

    def get_radios_lists(self, index=0, limit=25):
        return self.api_call('radio/lists', {'index': index, 'limit': limit})

    def get_radio(self, radio_id):
        return self.api_call(f'radio/{str(radio_id)}')

    def get_radio_tracks(self, radio_id, index=0, limit=40):
        return self.api_call(f'radio/{str(radio_id)}/tracks', {'index': index, 'limit': limit})

    def _generate_search_advanced_query(self, artist="", album="", track="", label="", dur_min=0, dur_max=0, bpm_min=0, bpm_max=0):
        query = ""
        if artist: query += f'artist:"{artist}" '
        if album: query += f'album:"{album}" '
        if track: query += f'track:"{track}" '
        if label: query += f'label:"{label}" '
        if dur_min: query += f'dur_min:"{str(dur_min)}" '
        if dur_max: query += f'dur_max:"{str(dur_max)}" '
        if bpm_min: query += f'bpm_min:"{str(bpm_min)}" '
        if bpm_max: query += f'bpm_max:"{str(bpm_max)}" '
        return query.strip()

    def _generate_search_args(self, query, strict=False, order=None, index=0, limit=25):
        args = {'q': query, 'index': index, 'limit': limit}
        if strict: args['strict'] = 'on'
        if order: args['order'] = order
        return args

    def search(self, query, strict=False, order=None, index=0, limit=25):
        args = self._generate_search_args(query, strict, order, index, limit)
        return self.api_call('search', args)

    def advanced_search(self, artist="", album="", track="", label="", dur_min=0, dur_max=0, bpm_min=0, bpm_max=0, strict=False, order=None, index=0, limit=25):
        query = self._generate_search_advanced_query(artist, album, track, label, dur_min, dur_max, bpm_min, bpm_max)
        return self.search(query, strict, order, index, limit)

    def search_album(self, query, strict=False, order=None, index=0, limit=25):
        args = self._generate_search_args(query, strict, order, index, limit)
        return self.api_call('search/album', args)

    def search_artist(self, query, strict=False, order=None, index=0, limit=25):
        args = self._generate_search_args(query, strict, order, index, limit)
        return self.api_call('search/artist', args)

    def search_playlist(self, query, strict=False, order=None, index=0, limit=25):
        args = self._generate_search_args(query, strict, order, index, limit)
        return self.api_call('search/playlist', args)

    def search_radio(self, query, strict=False, order=None, index=0, limit=25):
        args = self._generate_search_args(query, strict, order, index, limit)
        return self.api_call('search/radio', args)

    def search_track(self, query, strict=False, order=None, index=0, limit=25):
        args = self._generate_search_args(query, strict, order, index, limit)
        return self.api_call('search/track', args)

    def search_user(self, query, strict=False, order=None, index=0, limit=25):
        args = self._generate_search_args(query, strict, order, index, limit)
        return self.api_call('search/user', args)

    def get_track(self, song_id):
        return self.api_call(f'track/{str(song_id)}')

    def get_track_by_ISRC(self, isrc):
        return self.get_track(f'isrc:{isrc}')

    def get_user(self, user_id):
        return self.api_call(f'user/{str(user_id)}')

    def get_user_albums(self, user_id, index=0, limit=25):
        return self.api_call(f'user/{str(user_id)}/albums', {'index': index, 'limit': limit})

    def get_user_artists(self, user_id, index=0, limit=25):
        return self.api_call(f'user/{str(user_id)}/artists', {'index': index, 'limit': limit})

    def get_user_flow(self, user_id, index=0, limit=25):
        return self.api_call(f'user/{str(user_id)}/flow', {'index': index, 'limit': limit})

    def get_user_following(self, user_id, index=0, limit=25):
        return self.api_call(f'user/{str(user_id)}/followings', {'index': index, 'limit': limit})

    def get_user_followers(self, user_id, index=0, limit=25):
        return self.api_call(f'user/{str(user_id)}/followers', {'index': index, 'limit': limit})

    def get_user_playlists(self, user_id, index=0, limit=25):
        return self.api_call(f'user/{str(user_id)}/playlists', {'index': index, 'limit': limit})

    def get_user_radios(self, user_id, index=0, limit=25):
        return self.api_call(f'user/{str(user_id)}/radios', {'index': index, 'limit': limit})

    def get_user_tracks(self, user_id, index=0, limit=25):
        return self.api_call(f'user/{str(user_id)}/tracks', {'index': index, 'limit': limit})

    # Extra calls

    def get_countries_charts(self):
        temp = self.get_user_playlists('637006841', limit=-1)['data']
        result = sorted(temp, key=lambda k: k['title']) # Sort all playlists
        if not result[0]['title'].startswith('Top'): result = result[1:] # Remove loved tracks playlist
        return result

    def get_track_id_from_metadata(self, artist, track, album):
        artist = artist.replace("–", "-").replace("’", "'")
        track = track.replace("–", "-").replace("’", "'")
        album = album.replace("–", "-").replace("’", "'")

        resp = self.advanced_search(artist=artist, track=track, album=album, limit=1)
        if len(resp['data']) > 0: return resp['data'][0]['id']

        resp = self.advanced_search(artist=artist, track=track, limit=1)
        if len(resp['data']) > 0: return resp['data'][0]['id']

        # Try removing version
        if "(" in track and ")" in track and track.find("(") < track.find(")"):
            resp = self.advanced_search(artist=artist, track=track[:track.find("(")], limit=1)
            if len(resp['data']) > 0: return resp['data'][0]['id']
        elif " - " in track:
            resp = self.advanced_search(artist=artist, track=track[:track.find(" - ")], limit=1)
            if len(resp['data']) > 0: return resp['data'][0]['id']
        return "0"
