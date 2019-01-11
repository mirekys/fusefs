#!/usr/bin/env python
#
# #MIT License

# Copyright (c) 2019 Miroslav Bauer <bauer@cesnet.cz>

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
#
import os
import sys
import stat
import errno
import logging
import fs.errors

from fs.time import datetime_to_epoch
from fs.enums import ResourceType
from fs.opener import open_fs
from fs.permissions import Permissions
from fuse import FUSE, FuseOSError, Operations, LoggingMixIn


class FUSEFs(LoggingMixIn, Operations):

  def __init__(self, root, uid, gid):
      self.fs = open_fs(root)
      self.uid = uid
      self.gid = gid

  def destroy(self, path):
    self.fs.close()

  def access(self, path, mode):
    if self.fs.exists(path):
      if os.getuid() == self.uid:
        return True

    raise FuseOSError(errno.EACCES)

  def chmod(self, path, mode):
    perms = Permissions(mode)
    try:
      self.fs.setinfo(path, {'access': {'permissions': perms}})
    except fs.errors.ResourceReadOnly:
      raise FuseOSError(errno.EROFS)

  def chown(self, path, uid, gid):
    try:
      self.fs.setinfo(path, {'access': {'uid': uid, 'gid': gid}})
    except fs.errors.ResourceReadOnly:
      raise FuseOSError(errno.EROFS)

  def getattr(self, path, fh=None):
    try:
      info = self.fs.getinfo(path, namespaces=['access', 'details'])
      st = {
        'st_atime': datetime_to_epoch(info.accessed) if info.accessed else 0,
        'st_ctime': datetime_to_epoch(info.created) if info.created else 0,
        'st_mtime': datetime_to_epoch(info.modified) if info.modified else 0,
        'st_size': info.size or 0,
        'st_uid': self.uid,
        'st_gid': self.gid
        }

      if info.type == ResourceType.directory:
        st['st_nlink'] = 2
        st['st_mode'] = (stat.S_IFDIR | 0o755)
      elif info.type == ResourceType.file:
        st['st_nlink'] = 1
        st['st_mode'] = (stat.S_IFREG | 0o644)

      return(st)
    except fs.errors.ResourceNotFound:
      raise FuseOSError(errno.ENOENT)

  def readdir(self, path, fh):
    dirents = ['.', '..']
    try:
      if self.fs.getinfo(path).is_dir:
        dirents.extend(self.fs.listdir(path))
      for r in dirents:
        yield r
    except fs.errors.DirectoryExpected:
      raise FuseOSError(errno.ENOTDIR)
    except fs.errors.ResourceNotFound:
      raise FuseOSError(errno.ENOENT)

  def mknod(self, path, mode, dev):
    if dev != stat.S_IFREG:
      raise FuseOSError(errno.ENOSYS)
    with self.fs.lock():
      try:
          created = self.fs.create(path)
          self.chmod(path, mode)
      except fs.errors.ResourceReadOnly:
        raise FuseOSError(errno.EROFS)
    return created

  def rmdir(self, path):
    try:
      return self.fs.removedir(path)
    except fs.errors.DirectoryNotEmpty:
      raise FuseOSError(errno.ENOTEMPTY)
    except fs.errors.DirectoryExpected:
      raise FuseOSError(errno.ENOTDIR)
    except fs.errors.ResourceNotFound:
      raise FuseOSError(errno.ENOENT)
    except fs.errors.RemoveRootError:
      raise FuseOSError(errno.EACCES)
    except fs.errors.ResourceReadOnly:
      raise FuseOSError(errno.EROFS)

  def mkdir(self, path, mode):
    with self.fs.lock():
      try:
        created = self.fs.makedir(path)
        self.chmod(path, mode)
      except fs.errors.DirectoryExists:
        raise FuseOSError(errno.EEXIST)
      except fs.errors.ResourceNotFound:
        raise FuseOSError(errno.ENOENT)
      except fs.errors.ResourceReadOnly:
        raise FuseOSError(errno.EROFS)
    return created

  def unlink(self, path):
    try:
      return self.fs.remove(path)
    except fs.errors.ResourceNotFound:
      raise FuseOSError(errno.ENOENT)
    except fs.errors.FileExpected:
      raise FuseOSError(errno.EISDIR)
    except fs.errors.ResourceReadOnly:
      raise FuseOSError(errno.EROFS)

  def rename(self, old, new):
    try:
      return self.fs.move(old, new, overwrite=True)
    except fs.errors.FileExpected:
      raise FuseOSError(errno.EISDIR)
    except fs.errors.DestinationExists:
      raise FuseOSError(errno.EEXIST)
    except fs.errors.ResourceNotFound:
      raise FuseOSError(errno.ENOENT)
    except fs.errors.ResourceReadOnly:
      raise FuseOSError(errno.EROFS)

  def utimens(self, path, times=None):
    atime, mtime = times
    try:
      return self.fs.settimes(path, atime, mtime)
    except fs.errors.ResourceReadOnly:
      raise FuseOSError(errno.EROFS)

  def create(self, path, mode, fi=None):
    try:
      file = self.fs.open(path, 'wb')
    except fs.errors.ResourceReadOnly:
      raise FuseOSError(errno.EROFS)

    return file

  def read(self, path, length, offset, fh):
    try:
      with self.fs.openbin(path) as zipfile:
        zipfile.seek(offset)
        zip_bytes = zipfile.read(length)
    except fs.errors.ResourceNotFound:
      raise FuseOSError(errno.ENOENT)
    except fs.errors.FileExpected:
      raise FuseOSError(errno.EISDIR)

    return zip_bytes

  def write(self, path, buf, offset, fh):
    # Writing to ZIP not supported yet
    raise FuseOSError(errno.ENOSYS)

  def truncate(self, path, length, fh=None):
    try:
      return self.fs.create(path, wipe=True)
    except fs.errors.ResourceReadOnly:
      raise FuseOSError(errno.EROFS)

  # Disable unused operations
  symlink = None
  link = None
  fsync = None
  release = None
  flush = None
  readlink = None
  releasedir = None
  statfs = None
  getxattr = None
  listxattr = None


def main():
  if len(sys.argv) < 3 or len(sys.argv) > 4:
        print('usage: %s <source> <mountpoint> [--debug]' % sys.argv[0])
        exit(1)
  elif len(sys.argv) == 4 and sys.argv[3] == '--debug':
    logging.basicConfig(level=logging.DEBUG)

  FUSE(FUSEFs(sys.argv[1], os.getuid(), os.getgid()), sys.argv[2], nothreads=True, foreground=True)

if __name__ == '__main__':
  main()
