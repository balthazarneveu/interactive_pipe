import dbus
import sys
from sys import platform
import time


class SpotifyInterface():
    def factory(type):
        try:
            interface = dbus.Interface(
                dbus.SessionBus().get_object(
                    'org.mpris.MediaPlayer2.spotify',
                    '/org/mpris/MediaPlayer2'
                ),
                type
            )
        except dbus.exceptions.DBusException:
            sys.exit("\nSome errors occured. Try restart or start Spotify.\n")
        return interface
    factory = staticmethod(factory)


class SpotifyLinux():
    def __init__(self):
        self.interface = SpotifyInterface.factory(
            'org.mpris.MediaPlayer2.Player')

    def set_audio(self, audio_url):
        self.pause()
        if "http" in audio_url:
            audio_url = "spotify:track:" + \
                audio_url.split("track/")[1].split("?")[0]
        self.interface.OpenUri(audio_url)
        time.sleep(0.5)
        self.pause()

    def next(self):
        self.interface.Next()

    def prev(self):
        self.interface.Previous()

    def play_pause(self):
        self.interface.PlayPause()

    def pause(self):
        self.interface.Stop()

    def __del__(self):
        self.pause()


def get_spotify_music():
    if 'linux' in platform:
        return SpotifyLinux()
    else:
        raise Exception('%s is not supported.' % platform)
