# from __future__ import absolute_import, unicode_literals
import dbus
import sys
from sys import platform


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
            """
                If we catch this exception, Spotify is not running.
                Let the user know.
            """
            sys.exit(
                "\nSome errors occured. Try restart or start Spotify.\n"
            )

        return interface
    factory = staticmethod(factory)



class SpotifyLinux():
    def __init__(self):
        print("Spotify for linux")
        self.interface = SpotifyInterface.factory('org.mpris.MediaPlayer2.Player')

    def next(self):
        self.interface.Next()

    def prev(self):
        self.interface.Previous()

    def play_pause(self):
        self.interface.PlayPause()

    def pause(self):
        self.interface.Stop()

    def get_current_playing(self):
        return self.metadata.get_current_playing()

    def __del__(self):
        self.pause()


def get_music():
    if 'linux' in platform:
        return SpotifyLinux()
    else:
        raise Exception('%s is not supported.' % platform)