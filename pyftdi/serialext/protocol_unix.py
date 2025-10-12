# Copyright (c) 2008-2024, Emmanuel Blot <emmanuel.blot@free.fr>
# Copyright (c) 2016, Emmanuel Bouaziz <ebouaziz@free.fr>
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

# this file has not been updated for a while, so coding style needs some love
# pylint: disable=broad-except
# pylint: disable=attribute-defined-outside-init
# pylint: disable=redefined-outer-name
# pylint: disable=invalid-name
# pylint: disable=missing-function-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=missing-module-docstring

import errno
import os
import select
import socket
from io import RawIOBase
from typing import Optional, Union
from serial import (SerialBase, SerialException, PortNotOpenError,
                    VERSION as pyserialver)
from ..misc import hexdump


__all__ = ['Serial']


class SerialExceptionWithErrno(SerialException):
    """Serial exception with errno extension"""

    def __init__(self, message: str, errno: Optional[int] = None) -> None:
        SerialException.__init__(self, message)
        self.errno = errno


class SocketSerial(SerialBase):
    """Fake serial port redirected to a Unix socket.

       This is basically a copy of the serialposix serial port implementation
       with redefined IO for a Unix socket"""

    BACKEND: str = 'socket'
    VIRTUAL_DEVICE: bool = True

    PYSERIAL_VERSION: tuple = tuple(int(x) for x in pyserialver.split('.'))

    def _reconfigure_port(self) -> None:
        pass

    def open(self) -> None:
        """Open the initialized serial port"""
        if self._port is None:
            raise SerialException("Port must be configured before use.")
        if self.isOpen():
            raise SerialException("Port is already open.")
        self._dump = False
        self.sock = None
        try:
            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            filename = self.portstr[self.portstr.index('://')+3:]
            if filename.startswith('~/'):
                home = os.getenv('HOME')
                if home:
                    filename = os.path.join(home, filename[2:])
            self._filename = filename
            self.sock.connect(self._filename)
        except Exception as exc:
            self.close()
            msg = f'Could not open port: {exc}'
            if isinstance(exc, socket.error):
                # pylint: disable=no-member
                raise SerialExceptionWithErrno(msg, exc.errno) from exc
            raise SerialException(msg) from exc
        self._set_open_state(True)
        self._lastdtr = None

    def close(self) -> None:
        if self.sock:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
        self._set_open_state(False)

    def in_waiting(self) -> int:
        """Return the number of characters currently in the input buffer."""
        return 0

    def read(self, size: int = 1) -> Union[bytes, bytearray]:
        """Read size bytes from the serial port. If a timeout is set it may
           return less characters as requested. With no timeout it will block
           until the requested number of bytes is read."""
        if self.sock is None:
            raise PortNotOpenError
        read = bytearray()
        if size > 0:
            while len(read) < size:
                ready, _, _ = select.select([self.sock], [], [], self._timeout)
                if not ready:
                    break   # timeout
                buf = self.sock.recv(size-len(read))
                if not buf:
                    # Some character is ready, but none can be read
                    # it is a marker for a disconnected peer
                    raise PortNotOpenError
                read += buf
                if self._timeout >= 0 and not buf:
                    break  # early abort on timeout
        return read

    def write(self, data: Union[bytes, bytearray]) -> Optional[int]:
        """Output the given string over the serial port."""
        if self.sock is None:
            raise PortNotOpenError
        t = len(data)
        d = data
        while t > 0:
            try:
                if self.writeTimeout is not None and self.writeTimeout > 0:
                    _, ready, _ = select.select([], [self.sock], [],
                                                self.writeTimeout)
                    if not ready:
                        raise TimeoutError()
                n = self.sock.send(d)
                if self._dump:
                    print(hexdump(d[:n]))
                if self.writeTimeout is not None and self.writeTimeout > 0:
                    _, ready, _ = select.select([], [self.sock], [],
                                                self.writeTimeout)
                    if not ready:
                        raise TimeoutError()
                d = d[n:]
                t = t - n
            except OSError as e:
                if e.errno != errno.EAGAIN:
                    raise

    def flush(self) -> None:
        """Flush of file like objects. In this case, wait until all data
           is written."""

    def reset_input_buffer(self) -> None:
        """Clear input buffer, discarding all that is in the buffer."""

    def reset_output_buffer(self) -> None:
        """Clear output buffer, aborting the current output and
        discarding all that is in the buffer."""

    def send_break(self, duration: float = 0.25) -> None:
        """Send break condition. Not supported"""

    def _update_break_state(self) -> None:
        """Send break condition. Not supported"""

    def _update_rts_state(self) -> None:
        """Set terminal status line: Request To Send"""

    def _update_dtr_state(self) -> None:
        """Set terminal status line: Data Terminal Ready"""

    def setDTR(self, value: int = 1) -> None:
        """Set terminal status line: Data Terminal Ready"""

    @property
    def cts(self) -> bool:
        """Read terminal status line: Clear To Send"""
        return True

    @property
    def dsr(self) -> bool:
        """Read terminal status line: Data Set Ready"""
        return True

    @property
    def ri(self) -> bool:
        """Read terminal status line: Ring Indicator"""
        return False

    @property
    def cd(self) -> bool:
        """Read terminal status line: Carrier Detect"""
        return False

    # - - platform specific - - - -

    def nonblocking(self) -> None:
        """internal - not portable!"""
        if self.sock is None:
            raise PortNotOpenError
        self.sock.setblocking(0)

    def dump(self, enable: bool) -> None:
        self._dump = enable

    # - - Helpers - -

    def _set_open_state(self, open_: bool) -> None:
        if self.PYSERIAL_VERSION < (3, 0):
            self._isOpen = bool(open_)
        else:
            self.is_open = bool(open_)


# assemble Serial class with the platform specifc implementation and the base
# for file-like behavior.
class Serial(SocketSerial, RawIOBase):
    pass
