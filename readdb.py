# Copyright 2009 One Laptop Per Child
# Author: Sayamindu Dasgupta <sayamindu@laptop.org>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

import logging

import os
import shutil
import sqlite3
import time

from sugar3 import profile

from readbookmark import Bookmark

_logger = logging.getLogger('read-activity')


def _init_db():
    dbdir = os.path.join(os.environ['SUGAR_ACTIVITY_ROOT'], 'data')
    dbpath = os.path.join(dbdir, 'read_v1.db')
    olddbpath = os.path.join(dbdir, 'read.db')

    srcpath = os.path.join(os.environ['SUGAR_BUNDLE_PATH'], 'read_v1.db')

    #Situation 0: Db is existent
    if os.path.exists(dbpath):
        return dbpath

    #Situation 1: DB is non-existent at all
    if not os.path.exists(dbpath) and not os.path.exists(olddbpath):
        try:
            os.makedirs(dbdir)
        except:
            pass
        shutil.copy(srcpath, dbpath)
        return dbpath

    #Situation 2: DB is outdated
    if not os.path.exists(dbpath) and os.path.exists(olddbpath):
        shutil.copy(olddbpath, dbpath)

        conn = sqlite3.connect(dbpath)
        conn.execute("CREATE TABLE  temp_bookmarks  AS SELECT md5, page, " + \
            "title 'content', timestamp, user, color, local  FROM bookmarks")
        conn.execute("ALTER TABLE bookmarks RENAME TO bookmarks_old")
        conn.execute("ALTER TABLE temp_bookmarks RENAME TO bookmarks")
        conn.execute("DROP TABLE bookmarks_old")
        conn.commit()
        conn.close()

        return dbpath

    # Should not reach this point
    return None


def _init_db_highlights(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS HIGHLIGHTS ' +
                '(md5 TEXT, page INTEGER, ' +
                'init_pos INTEGER, end_pos INTEGER)')
    conn.commit()


class BookmarkManager:

    def __init__(self, filehash):
        self._filehash = filehash

        dbpath = _init_db()

        assert dbpath != None

        self._conn = sqlite3.connect(dbpath)
        _init_db_highlights(self._conn)

        self._conn.text_factory = lambda x: unicode(x, "utf-8", "ignore")

        self._bookmarks = []
        self._populate_bookmarks()
        self._highlights = {0:  []}
        self._populate_highlights()

        self._user = profile.get_nick_name()
        self._color = profile.get_color().to_string()

    def add_bookmark(self, page, content, local=1):
        # locale = 0 means that this is a bookmark originally
        # created by the person who originally shared the file
        timestamp = time.time()
        t = (self._filehash, page, content, timestamp, self._user, \
                self._color, local)
        self._conn.execute('insert into bookmarks values ' + \
                '(?, ?, ?, ?, ?, ?, ?)', t)
        self._conn.commit()

        self._resync_bookmark_cache()

    def del_bookmark(self, page):
        # We delete only the locally made bookmark

        t = (self._filehash, page, self._user)
        self._conn.execute('delete from bookmarks ' + \
                'where md5=? and page=? and user=?', t)
        self._conn.commit()

        self._resync_bookmark_cache()

    def _populate_bookmarks(self):
        # TODO: Figure out if caching the entire set of bookmarks
        # is a good idea or not
        rows = self._conn.execute('select * from bookmarks ' + \
            'where md5=? order by page', (self._filehash, ))

        for row in rows:
            self._bookmarks.append(Bookmark(row))

    def get_bookmarks_for_page(self, page):
        bookmarks = []
        for bookmark in self._bookmarks:
            if bookmark.belongstopage(page):
                bookmarks.append(bookmark)

        return bookmarks

    def _resync_bookmark_cache(self):
        # To be called when a new bookmark has been added/removed
        self._bookmarks = []
        self._populate_bookmarks()

    def get_prev_bookmark_for_page(self, page, wrap=True):
        if not len(self._bookmarks):
            return None

        if page <= self._bookmarks[0].page_no and wrap:
            return self._bookmarks[-1]
        else:
            for i in range(page - 1, -1, -1):
                for bookmark in self._bookmarks:
                    if bookmark.belongstopage(i):
                        return bookmark

        return None

    def get_next_bookmark_for_page(self, page, wrap=True):
        if not len(self._bookmarks):
            return None

        if page >= self._bookmarks[-1].page_no and wrap:
            return self._bookmarks[0]
        else:
            for i in range(page + 1, self._bookmarks[-1].page_no + 1):
                for bookmark in self._bookmarks:
                    if bookmark.belongstopage(i):
                        return bookmark

        return None

    def get_highlights(self, page):
        try:
            return self._highlights[page]
        except KeyError:
            self._highlights[page] = []
            return self._highlights[page]

    def add_highlight(self, page, highlight_tuple):
        logging.error('Adding hg page %d %s' % (page, highlight_tuple))
        self.get_highlights(page).append(highlight_tuple)

        t = (self._filehash, page, highlight_tuple[0],
                highlight_tuple[1])
        self._conn.execute('insert into highlights values ' + \
                '(?, ?, ?, ?)', t)
        self._conn.commit()

    def del_highlight(self, page, highlight_tuple):
        self._highlights[page].remove(highlight_tuple)
        t = (self._filehash, page, highlight_tuple[0], \
                highlight_tuple[1])
        self._conn.execute('delete from highlights ' + \
            'where md5=? and page=? and init_pos=? and end_pos=?', \
            t)
        self._conn.commit()

    def _populate_highlights(self):
        rows = self._conn.execute('select * from highlights ' + \
            'where md5=? order by page', (self._filehash, ))
        for row in rows:
            # md5 = row[0]
            page = row[1]
            init_pos = row[2]
            end_pos = row[3]
            highlight_tuple = [init_pos, end_pos]
            self.get_highlights(page).append(highlight_tuple)
