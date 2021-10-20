#!/usr/bin/env python
#
# Electrum - lightweight ILCOIN client
# Copyright (C) 2012 thomasv@gitorious
#
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation files
# (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify, merge,
# publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
# BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# Kivy GUI

import sys
import os
from typing import TYPE_CHECKING

try:
    sys.argv = ['']
    import kivy
except ImportError:
    # This error ideally shouldn't be raised with pre-built packages
    sys.exit("Error: Could not import kivy. Please install it using the "
             "instructions mentioned here `https://kivy.org/#download` .")

# minimum required version for kivy
kivy.require('1.8.0')

from electrum.logging import Logger

if TYPE_CHECKING:
    from electrum.simple_config import SimpleConfig
    from electrum.daemon import Daemon
    from electrum.plugin import Plugins




class ElectrumGui(Logger):

    def __init__(self, config: 'SimpleConfig', daemon: 'Daemon', plugins: 'Plugins'):
        Logger.__init__(self)
        self.logger.debug('ElectrumGUI: initialising')
        self.daemon = daemon
        self.network = daemon.network
        self.config = config
        self.plugins = plugins

    def main(self):
        from .main_window import ElectrumWindow
        w = ElectrumWindow(config=self.config,
                           network=self.network,
                           plugins = self.plugins,
                           gui_object=self)
        w.run()

    def stop(self):
        pass
