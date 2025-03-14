import re

class DefaultDict(dict):
    def __getitem__(self, key):
        return self.get(key, None)

class LyricsStatus():
    """Explicit Content Lyrics"""

    NOT_EXPLICIT = 0
    """Not Explicit"""

    EXPLICIT = 1
    """Explicit"""

    UNKNOWN = 2
    """Unknown"""

    EDITED = 3
    """Edited"""

    PARTIALLY_EXPLICIT = 4
    """Partially Explicit (Album "lyrics" only)"""

    PARTIALLY_UNKNOWN = 5
    """Partially Unknown (Album "lyrics" only)"""

    NO_ADVICE = 6
    """No Advice Available"""

    PARTIALLY_NO_ADVICE = 7
    """Partially No Advice Available (Album "lyrics" only)"""

ReleaseType = {0:"single", 1:"album", 2:"compile", 3:"ep", 4:"bundle"}

# TODO: add missing role ids
RoleID = {"0":"Main", "5":"Featured"}

def is_explicit(explicit_content_lyrics):
    """get explicit lyrics boolean from explicit_content_lyrics"""
    return explicit_content_lyrics or LyricsStatus.UNKNOWN in [LyricsStatus.EXPLICIT, LyricsStatus.PARTIALLY_EXPLICIT]

def map_user_track(track):
    """maps gw-light api user/tracks to standard api"""
    track = DefaultDict(track)
    result = {
        'id': track['SNG_ID'],
        'title': track['SNG_TITLE'],
        'link': 'https://www.deezer.com/track/'+str(track['SNG_ID']),
        'duration': track['DURATION'],
        'rank': track['RANK_SNG'],
        'explicit_lyrics': False,
        'explicit_content_lyrics': False,
        'explicit_content_cover': False,
        'time_add': track.get('DATE_ADD') or track.get('DATE_FAVORITE'),
        'album': {
                'id': track['ALB_ID'],
                'title': track['ALB_TITLE'],
                'cover': 'https://api.deezer.com/album/'+str(track['ALB_ID'])+'/image',
                'cover_small': 'https://e-cdns-images.dzcdn.net/images/cover/'+str(track['ALB_PICTURE'])+'/56x56-000000-80-0-0.jpg',
                'cover_medium': 'https://e-cdns-images.dzcdn.net/images/cover/'+str(track['ALB_PICTURE'])+'/250x250-000000-80-0-0.jpg',
                'cover_big': 'https://e-cdns-images.dzcdn.net/images/cover/'+str(track['ALB_PICTURE'])+'/500x500-000000-80-0-0.jpg',
                'cover_xl': 'https://e-cdns-images.dzcdn.net/images/cover/'+str(track['ALB_PICTURE'])+'/1000x1000-000000-80-0-0.jpg',
                'tracklist': 'https://api.deezer.com/album/'+str(track['ALB_ID'])+'/tracks',
                'type': 'album'
        },
        'artist': {
                'id': track['ART_ID'],
                'name': track['ART_NAME'],
                'picture': 'https://api.deezer.com/artist/'+str(track['ART_ID'])+'/image',
                'picture_small': None,
                'picture_medium': None,
                'picture_big': None,
                'picture_xl': None,
                'tracklist': 'https://api.deezer.com/artist/'+str(track['ART_ID'])+'/top?limit=50',
                'type': 'artist'
        },
        'type': 'track'
    }
    if int(track['SNG_ID']) >= 0:
        art_picture = track.get('ART_PICTURE')
        if not art_picture:
            for artist in track.get('ARTISTS', []):
                artist = DefaultDict(artist)
                if artist['ART_ID'] == track['ART_ID']:
                    art_picture = artist['ART_PICTURE']
                    break
        result['explicit_lyrics'] = is_explicit(track['EXPLICIT_LYRICS'])
        result['explicit_content_lyrics'] = track.get('EXPLICIT_TRACK_CONTENT', {}).get('EXPLICIT_COVER_STATUS')
        result['explicit_content_cover'] = track.get('EXPLICIT_TRACK_CONTENT', {}).get('EXPLICIT_LYRICS_STATUS')

        result['artist']['picture_small'] = 'https://e-cdns-images.dzcdn.net/images/artist/'+str(art_picture)+'/56x56-000000-80-0-0.jpg'
        result['artist']['picture_medium'] = 'https://e-cdns-images.dzcdn.net/images/artist/'+str(art_picture)+'/250x250-000000-80-0-0.jpg'
        result['artist']['picture_big'] = 'https://e-cdns-images.dzcdn.net/images/artist/'+str(art_picture)+'/500x500-000000-80-0-0.jpg'
        result['artist']['picture_xl'] = 'https://e-cdns-images.dzcdn.net/images/artist/'+str(art_picture)+'/1000x1000-000000-80-0-0.jpg'
    return result

def map_user_artist(artist):
    """maps gw-light api user/artists to standard api"""
    artist = DefaultDict(artist)
    return {
        'id': artist['ART_ID'],
        'name': artist['ART_NAME'],
        'link': 'https://www.deezer.com/artist/'+str(artist['ART_ID']),
        'picture': 'https://api.deezer.com/artist/'+str(artist['ART_ID'])+'/image',
        'picture_small': 'https://e-cdns-images.dzcdn.net/images/artist/'+str(artist['ART_PICTURE'])+'/56x56-000000-80-0-0.jpg',
        'picture_medium': 'https://e-cdns-images.dzcdn.net/images/artist/'+str(artist['ART_PICTURE'])+'/250x250-000000-80-0-0.jpg',
        'picture_big': 'https://e-cdns-images.dzcdn.net/images/artist/'+str(artist['ART_PICTURE'])+'/500x500-000000-80-0-0.jpg',
        'picture_xl': 'https://e-cdns-images.dzcdn.net/images/artist/'+str(artist['ART_PICTURE'])+'/1000x1000-000000-80-0-0.jpg',
        'nb_fan': artist['NB_FAN'],
        'tracklist': 'https://api.deezer.com/artist/'+str(artist['ART_ID'])+'/top?limit=50',
        'type': 'artist'
    }

def map_user_album(album):
    """maps gw-light api user/albums to standard api"""
    album = DefaultDict(album)
    return {
        'id': album['ALB_ID'],
        'title': album['ALB_TITLE'],
        'link': 'https://www.deezer.com/album/'+str(album['ALB_ID']),
        'cover': 'https://api.deezer.com/album/'+str(album['ALB_ID'])+'/image',
        'cover_small': 'https://e-cdns-images.dzcdn.net/images/cover/'+album['ALB_PICTURE']+'/56x56-000000-80-0-0.jpg',
        'cover_medium': 'https://e-cdns-images.dzcdn.net/images/cover/'+album['ALB_PICTURE']+'/250x250-000000-80-0-0.jpg',
        'cover_big': 'https://e-cdns-images.dzcdn.net/images/cover/'+album['ALB_PICTURE']+'/500x500-000000-80-0-0.jpg',
        'cover_xl': 'https://e-cdns-images.dzcdn.net/images/cover/'+album['ALB_PICTURE']+'/1000x1000-000000-80-0-0.jpg',
        'tracklist': 'https://api.deezer.com/album/'+str(album['ALB_ID'])+'/tracks',
        'explicit_lyrics': is_explicit(album['EXPLICIT_ALBUM_CONTENT']['EXPLICIT_LYRICS_STATUS']),
        'artist': {
            'id': album['ART_ID'],
            'name': album['ART_NAME'],
            'picture': 'https://api.deezer.com/artist/'+str(album['ART_ID'])+'image',
            'tracklist': 'https://api.deezer.com/artist/'+str(album['ART_ID'])+'/top?limit=50'
        },
        'type': 'album'
    }

def map_user_playlist(playlist, default_user_name=""):
    """maps gw-light api user/playlists to standard api"""
    playlist = DefaultDict(playlist)
    return {
        'id': playlist['PLAYLIST_ID'],
        'title': playlist['TITLE'],
        'description': playlist.get('DESCRIPTION', ''),
        'nb_tracks': playlist['NB_SONG'],
        'link': 'https://www.deezer.com/playlist/'+str(playlist['PLAYLIST_ID']),
        'picture': 'https://api.deezer.com/playlist/'+str(playlist['PLAYLIST_ID'])+'/image',
        'picture_small': 'https://e-cdns-images.dzcdn.net/images/'+playlist['PICTURE_TYPE']+'/'+playlist['PLAYLIST_PICTURE']+'/56x56-000000-80-0-0.jpg',
        'picture_medium': 'https://e-cdns-images.dzcdn.net/images/'+playlist['PICTURE_TYPE']+'/'+playlist['PLAYLIST_PICTURE']+'/250x250-000000-80-0-0.jpg',
        'picture_big': 'https://e-cdns-images.dzcdn.net/images/'+playlist['PICTURE_TYPE']+'/'+playlist['PLAYLIST_PICTURE']+'/500x500-000000-80-0-0.jpg',
        'picture_xl': 'https://e-cdns-images.dzcdn.net/images/'+playlist['PICTURE_TYPE']+'/'+playlist['PLAYLIST_PICTURE']+'/1000x1000-000000-80-0-0.jpg',
        'tracklist': 'https://api.deezer.com/playlist/'+str(playlist['PLAYLIST_ID'])+'/tracks',
        'creation_date': playlist['DATE_ADD'],
        'creator': {
            'id': playlist['PARENT_USER_ID'],
            'name': playlist.get('PARENT_USERNAME', default_user_name)
        },
        'type': 'playlist'
    }

def map_album(album):
    """maps gw-light api albums to standard api"""
    album = DefaultDict(album)
    result = {
        'id': album['ALB_ID'],
        'title': album['ALB_TITLE'],
        'title_short': album['ALB_TITLE'],
        'link': f"https://www.deezer.com/album/{album['ALB_ID']}",
        'share': f"https://www.deezer.com/album/{album['ALB_ID']}",
        'cover': f"https://api.deezer.com/album/{album['ALB_ID']}/image",
        'cover_small': f"https://cdns-images.dzcdn.net/images/cover/{album['ALB_PICTURE']}/56x56-000000-80-0-0.jpg",
        'cover_medium': f"https://cdns-images.dzcdn.net/images/cover/{album['ALB_PICTURE']}/250x250-000000-80-0-0.jpg",
        'cover_big': f"https://cdns-images.dzcdn.net/images/cover/{album['ALB_PICTURE']}/500x500-000000-80-0-0.jpg",
        'cover_xl': f"https://cdns-images.dzcdn.net/images/cover/{album['ALB_PICTURE']}/1000x1000-000000-80-0-0.jpg",
        'md5_image': album['ALB_PICTURE'],
        'genres': {}, # Not provided
        'label': album.get('LABEL_NAME'),
        'duration': None, # Not provided
        'fans': album.get('NB_FAN'),
        'release_date': album['PHYSICAL_RELEASE_DATE'],
        'record_type': None, # Not provided
        'alternative': None, # Not provided
        'tracklist': f"https://api.deezer.com/album/{album['ALB_ID']}/tracks",
        'explicit_lyrics': is_explicit(album.get('EXPLICIT_LYRICS')),
        'explicit_content_lyrics': album.get('EXPLICIT_ALBUM_CONTENT', {}).get('EXPLICIT_LYRICS_STATUS'),
        'explicit_content_cover': album.get('EXPLICIT_ALBUM_CONTENT', {}).get('EXPLICIT_COVER_STATUS'),
        'contributors': [],
        'artist': {
            'id': album['ART_ID'],
            'name': album['ART_NAME'],
            'link': f"https://www.deezer.com/artist/{album['ART_ID']}",
            'type': "artist",
            # Extras
            'rank': album.get('RANK_ART')
        },
        'type': album['__TYPE__'],
        'tracks': [], # not provided
        # Extras
        'rating': album.get('RANK'),
        'digital_release_date': album['DIGITAL_RELEASE_DATE'],
        'physical_release_date': album['PHYSICAL_RELEASE_DATE'],
        'original_release_date': album['ORIGINAL_RELEASE_DATE'],
    }
    result['title_version'] = album.get('VERSION', "").strip()
    if (result['title_version'] != "" and result['title_version'] in result['title_short']):
        result['title_short'] = result['title_short'].replace(result['title_version'], "").strip()
    result['title'] = f"{result['title_short']} {result['title_version']}".strip()
    result['upc'] = album.get('UPC')
    result['genre_id'] = album.get('GENRE_ID')
    result['nb_tracks'] = album.get('NUMBER_TRACK')
    result['available'] = album.get('AVAILABLE')
    result['album_contributors'] = album.get('ALB_CONTRIBUTORS')
    if album.get('NUMBER_DISK'): result['nb_disk'] = album['NUMBER_DISK']
    result['copyright'] = album.get('COPYRIGHT')
    if "ARTISTS" in album:
        for contributor in album['ARTISTS']:
            if contributor['ART_ID'] == result['artist']['id']:
                result['artist']['picture_small'] = f"https://e-cdns-images.dzcdn.net/images/artist/{contributor['ART_PICTURE']}/56x56-000000-80-0-0.jpg"
                result['artist']['picture_medium'] = f"https://e-cdns-images.dzcdn.net/images/artist/{contributor['ART_PICTURE']}/250x250-000000-80-0-0.jpg"
                result['artist']['picture_big'] = f"https://e-cdns-images.dzcdn.net/images/artist/{contributor['ART_PICTURE']}/500x500-000000-80-0-0.jpg"
                result['artist']['picture_xl'] = f"https://e-cdns-images.dzcdn.net/images/artist/{contributor['ART_PICTURE']}/1000x1000-000000-80-0-0.jpg"
                result['artist']['md5_image'] = contributor['ART_PICTURE']
            result['contributors'].append({
                'id': contributor['ART_ID'],
                'name': contributor['ART_NAME'],
                'link': f"https://www.deezer.com/artist/{contributor['ART_ID']}",
                'share': f"https://www.deezer.com/artist/{contributor['ART_ID']}",
                'picture': f"https://www.deezer.com/artist/{contributor['ART_ID']}/image",
                'picture_small': f"https://e-cdns-images.dzcdn.net/images/artist/{contributor['ART_PICTURE']}/56x56-000000-80-0-0.jpg",
                'picture_medium': f"https://e-cdns-images.dzcdn.net/images/artist/{contributor['ART_PICTURE']}/250x250-000000-80-0-0.jpg",
                'picture_big': f"https://e-cdns-images.dzcdn.net/images/artist/{contributor['ART_PICTURE']}/500x500-000000-80-0-0.jpg",
                'picture_xl': f"https://e-cdns-images.dzcdn.net/images/artist/{contributor['ART_PICTURE']}/1000x1000-000000-80-0-0.jpg",
                'md5_image': contributor['ART_PICTURE'],
                'tracklist': f"https://api.deezer.com/artist/{contributor['ART_ID']}/top?limit=50",
                'type': "artist",
                'role': RoleID.get(contributor['ROLE_ID']),
                # Extras
                'order': contributor.get('ARTISTS_SONGS_ORDER'),
                'rank': contributor.get('RANK')
            })
    return result

def map_artist_album(album):
    """maps gw-light api artist/albums to standard api"""
    album = DefaultDict(album)
    return {
        'id': album['ALB_ID'],
        'title': album['ALB_TITLE'],
        'link': f"https://www.deezer.com/album/{album['ALB_ID']}",
        'cover': f"https://api.deezer.com/album/{album['ALB_ID']}/image",
        'cover_small': f"https://cdns-images.dzcdn.net/images/cover/{album['ALB_PICTURE']}/56x56-000000-80-0-0.jpg",
        'cover_medium': f"https://cdns-images.dzcdn.net/images/cover/{album['ALB_PICTURE']}/250x250-000000-80-0-0.jpg",
        'cover_big': f"https://cdns-images.dzcdn.net/images/cover/{album['ALB_PICTURE']}/500x500-000000-80-0-0.jpg",
        'cover_xl': f"https://cdns-images.dzcdn.net/images/cover/{album['ALB_PICTURE']}/1000x1000-000000-80-0-0.jpg",
        'md5_image': album['ALB_PICTURE'],
        'genre_id': album['GENRE_ID'],
        'fans': None, # Not provided
        'release_date': album['PHYSICAL_RELEASE_DATE'],
        'record_type': ReleaseType.get(int(album['TYPE']), "unknown"),
        'tracklist': f"https://api.deezer.com/album/{album['ALB_ID']}/tracks",
        'explicit_lyrics': is_explicit(album['EXPLICIT_LYRICS']),
        'type': album['__TYPE__'],
        # Extras
        'nb_tracks': album['NUMBER_TRACK'],
        'nb_disk': album['NUMBER_DISK'],
        'copyright': album['COPYRIGHT'],
        'rank': album['RANK'],
        'digital_release_date': album['DIGITAL_RELEASE_DATE'],
        'original_release_date': album['ORIGINAL_RELEASE_DATE'],
        'physical_release_date': album['PHYSICAL_RELEASE_DATE'],
        'is_official': album['ARTISTS_ALBUMS_IS_OFFICIAL'],
        'explicit_content_cover': album['EXPLICIT_ALBUM_CONTENT']['EXPLICIT_LYRICS_STATUS'],
        'explicit_content_lyrics': album['EXPLICIT_ALBUM_CONTENT']['EXPLICIT_COVER_STATUS'],
        'artist_role': RoleID.get(album['ROLE_ID'])
    }

def map_playlist(playlist):
    """maps gw-light api playlists to standard api"""
    playlist = DefaultDict(playlist)
    return {
            'id': playlist['PLAYLIST_ID'],
            'title': playlist['TITLE'],
            'description': playlist['DESCRIPTION'],
            'duration': playlist['DURATION'],
            'public': playlist['STATUS'] == 1,
            'is_loved_track': playlist['TYPE'] == 4,
            'collaborative': playlist['STATUS'] == 2,
            'nb_tracks': playlist['NB_SONG'],
            'fans': playlist['NB_FAN'],
            'link': "https://www.deezer.com/playlist/"+playlist['PLAYLIST_ID'],
            'share': "https://www.deezer.com/playlist/"+playlist['PLAYLIST_ID'],
            'picture': "https://api.deezer.com/playlist/"+playlist['PLAYLIST_ID']+"/image",
            'picture_small': "https://cdns-images.dzcdn.net/images/"+playlist['PICTURE_TYPE']+"/"+playlist['PLAYLIST_PICTURE']+"/56x56-000000-80-0-0.jpg",
            'picture_medium': "https://cdns-images.dzcdn.net/images/"+playlist['PICTURE_TYPE']+"/"+playlist['PLAYLIST_PICTURE']+"/250x250-000000-80-0-0.jpg",
            'picture_big': "https://cdns-images.dzcdn.net/images/"+playlist['PICTURE_TYPE']+"/"+playlist['PLAYLIST_PICTURE']+"/500x500-000000-80-0-0.jpg",
            'picture_xl': "https://cdns-images.dzcdn.net/images/"+playlist['PICTURE_TYPE']+"/"+playlist['PLAYLIST_PICTURE']+"/1000x1000-000000-80-0-0.jpg",
            'md5_image': playlist['PLAYLIST_PICTURE'],
            'picture_type': playlist['PICTURE_TYPE'],
            'checksum': playlist['CHECKSUM'],
            'tracklist': "https://api.deezer.com/playlist/"+playlist['PLAYLIST_ID']+"/tracks",
            'creation_date': playlist['DATE_ADD'],
            'creator': {
                'id': playlist['PARENT_USER_ID'],
                'name': playlist['PARENT_USERNAME'],
                'tracklist': "https://api.deezer.com/user/"+playlist['PARENT_USER_ID']+"/flow",
                'type': "user"
            },
            'type': "playlist"
        }

def map_track(track):
    """maps gw-light api tracks to standard api"""
    track = DefaultDict(track)
    result = {
        'id': track['SNG_ID'],
        'readable': True, # not provided
        'title': track['SNG_TITLE'],
        'title_short': track['SNG_TITLE'],
        'isrc': track['ISRC'],
        'link': f"https://www.deezer.com/track/{track['SNG_ID']}",
        'share': f"https://www.deezer.com/track/{track['SNG_ID']}",
        'duration': track['DURATION'],
        'bpm': None, # not provided
        'available_countries': [], # not provided
        'contributors': [],
        'md5_image': track['ALB_PICTURE'],
        'artist': {
            'id': track['ART_ID'],
            'name': track['ART_NAME'],
            'link': f"https://www.deezer.com/artist/{track['ART_ID']}",
            'share': f"https://www.deezer.com/artist/{track['ART_ID']}",
            'picture': f"https://www.deezer.com/artist/{track['ART_ID']}/image",
            'radio': None, # not provided
            'tracklist': f"https://api.deezer.com/artist/{track['ART_ID']}/top?limit=50",
            'type': "artist"
        },
        'album': {
            'id': track['ALB_ID'],
            'title': track['ALB_TITLE'],
            'link': f"https://www.deezer.com/album/{track['ALB_ID']}",
            'cover': f"https://api.deezer.com/album/{track['ALB_ID']}/image",
            'cover_small': f"https://e-cdns-images.dzcdn.net/images/cover/{track['ALB_PICTURE']}/56x56-000000-80-0-0.jpg",
            'cover_medium': f"https://e-cdns-images.dzcdn.net/images/cover/{track['ALB_PICTURE']}/250x250-000000-80-0-0.jpg",
            'cover_big': f"https://e-cdns-images.dzcdn.net/images/cover/{track['ALB_PICTURE']}/500x500-000000-80-0-0.jpg",
            'cover_xl': f"https://e-cdns-images.dzcdn.net/images/cover/{track['ALB_PICTURE']}/1000x1000-000000-80-0-0.jpg",
            'md5_image': track['ALB_PICTURE'],
            'release_date': None, # not provided
            'tracklist': f"https://api.deezer.com/album/{track['ALB_ID']}/tracks",
            'type': "album"
        },
        'type': "track",
        # Extras
        'md5_origin': track['MD5_ORIGIN'],
        'filesizes': {
            'default': track['FILESIZE']
        },
        'media_version': track['MEDIA_VERSION'],
        'track_token': track['TRACK_TOKEN'],
        'track_token_expire': track['TRACK_TOKEN_EXPIRE']
      }
    if int(track['SNG_ID']) > 0:
        result['title_version'] = track.get('VERSION', "").strip()
        if result['title_version'] != "" and result['title_version'] in result['title_short']:
            result['title_short'] = result['title_short'].replace(result['title_version'], "").strip()
        result['title'] = f"{result['title_short']} {result['title_version']}".strip()
        result['track_position'] = track.get('TRACK_NUMBER', 0)
        result['disk_number'] = track.get('DISK_NUMBER', 0)
        result['rank'] = track.get('RANK') or track.get('RANK_SNG')
        result['release_date'] = track.get('PHYSICAL_RELEASE_DATE')
        result['explicit_lyrics'] = is_explicit(track['EXPLICIT_LYRICS'])
        result['explicit_content_lyrics'] = track.get('EXPLICIT_TRACK_CONTENT', {}).get('EXPLICIT_LYRICS_STATUS')
        result['explicit_content_cover'] = track.get('EXPLICIT_TRACK_CONTENT', {}).get('EXPLICIT_COVER_STATUS')
        result['preview'] = track['MEDIA'][0]['HREF']
        result['gain'] = track.get('GAIN')
        if 'ARTISTS' in track:
            for contributor in track['ARTISTS']:
                contributor = DefaultDict(contributor)
                if contributor['ART_ID'] == result['artist']['id']:
                    result['artist']['picture_small'] = f"https://e-cdns-images.dzcdn.net/images/artist/{contributor['ART_PICTURE']}/56x56-000000-80-0-0.jpg"
                    result['artist']['picture_medium'] = f"https://e-cdns-images.dzcdn.net/images/artist/{contributor['ART_PICTURE']}/250x250-000000-80-0-0.jpg"
                    result['artist']['picture_big'] = f"https://e-cdns-images.dzcdn.net/images/artist/{contributor['ART_PICTURE']}/500x500-000000-80-0-0.jpg"
                    result['artist']['picture_xl'] = f"https://e-cdns-images.dzcdn.net/images/artist/{contributor['ART_PICTURE']}/1000x1000-000000-80-0-0.jpg"
                    result['artist']['md5_image'] = contributor['ART_PICTURE']
                result['contributors'].append({
                    'id': contributor['ART_ID'],
                    'name': contributor['ART_NAME'],
                    'link': f"https://www.deezer.com/artist/{contributor['ART_ID']}",
                    'share': f"https://www.deezer.com/artist/{contributor['ART_ID']}",
                    'picture': f"https://www.deezer.com/artist/{contributor['ART_ID']}/image",
                    'picture_small': f"https://e-cdns-images.dzcdn.net/images/artist/{contributor['ART_PICTURE']}/56x56-000000-80-0-0.jpg",
                    'picture_medium': f"https://e-cdns-images.dzcdn.net/images/artist/{contributor['ART_PICTURE']}/250x250-000000-80-0-0.jpg",
                    'picture_big': f"https://e-cdns-images.dzcdn.net/images/artist/{contributor['ART_PICTURE']}/500x500-000000-80-0-0.jpg",
                    'picture_xl': f"https://e-cdns-images.dzcdn.net/images/artist/{contributor['ART_PICTURE']}/1000x1000-000000-80-0-0.jpg",
                    'md5_image': contributor['ART_PICTURE'],
                    'tracklist': f"https://api.deezer.com/artist/{contributor['ART_ID']}/top?limit=50",
                    'type': "artist",
                    'role': RoleID[contributor['ROLE_ID']],
                    # Extras
                    'order': contributor['ARTISTS_SONGS_ORDER'],
                    'rank': contributor['RANK']
                })
        # Extras
        result['lyrics_id'] = track['LYRICS_ID']
        result['physical_release_date'] = track['PHYSICAL_RELEASE_DATE']
        result['song_contributors'] = track['SNG_CONTRIBUTORS']
        if 'FALLBACK' in track: result['fallback_id'] = track.get('FALLBACK').get('SNG_ID')
        if 'DIGITAL_RELEASE_DATE' in track: result['digital_release_date'] = track['DIGITAL_RELEASE_DATE']
        if 'GENRE_ID' in track: result['genre_id'] = track['GENRE_ID']
        if 'COPYRIGHT' in track: result['copyright'] = track['COPYRIGHT']
        if 'LYRICS' in track: result['lyrics'] = track['LYRICS']
        if 'ALBUM_FALLBACK' in track: result['alternative_albums'] = track['ALBUM_FALLBACK']
        result['filesizes']['aac_64'] = track['FILESIZE_AAC_64']
        result['filesizes']['mp3_64'] = track['FILESIZE_MP3_64']
        result['filesizes']['mp3_128'] = track['FILESIZE_MP3_128']
        result['filesizes']['mp3_256'] = track['FILESIZE_MP3_256']
        result['filesizes']['mp3_320'] = track['FILESIZE_MP3_320']
        result['filesizes']['mp4_ra1'] = track.get('FILESIZE_MP4_RA1')
        result['filesizes']['mp4_ra2'] = track.get('FILESIZE_MP4_RA2')
        result['filesizes']['mp4_ra3'] = track.get('FILESIZE_MP4_RA3')
        result['filesizes']['flac'] = track['FILESIZE_FLAC']
    else:
        result['token'] = track['TOKEN']
        result['user_id'] = track['USER_ID']
        result['filesizes']['mp3_misc'] = track['FILESIZE_MP3_MISC']
    return result

def clean_search_query(term):
    """Cleanup terms that can hurt search results"""
    term = str(term)
    term = re.sub(r' feat[\.]? ', " ", term)
    term = re.sub(r' ft[\.]? ', " ", term)
    term = re.sub(r'\(feat[\.]? ', " ", term)
    term = re.sub(r'\(ft[\.]? ', " ", term)
    term = term.replace(' & ', " ").replace('–', "-").replace('—', "-")
    return term
