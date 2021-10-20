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

from typing import TYPE_CHECKING

from PyQt5.QtWidgets import QVBoxLayout, QLabel

from electrum.i18n import _

from .util import WindowModalDialog, ButtonsLineEdit, ColorScheme, Buttons, CloseButton
from .history_list import HistoryList, HistoryModel
from .qrtextedit import ShowQRTextEdit

if TYPE_CHECKING:
    from .main_window import ElectrumWindow


class AddressHistoryModel(HistoryModel):
    def __init__(self, parent: 'ElectrumWindow', address):
        super().__init__(parent)
        self.address = address

    def get_domain(self):
        return [self.address]

    def should_include_lightning_payments(self) -> bool:
        return False


class AddressDialog(WindowModalDialog):

    def __init__(self, parent: 'ElectrumWindow', address: str):
        WindowModalDialog.__init__(self, parent, _("Address"))
        self.address = address
        self.parent = parent
        self.config = parent.config
        self.wallet = parent.wallet
        self.app = parent.app
        self.saved = True

        self.setMinimumWidth(700)
        vbox = QVBoxLayout()
        self.setLayout(vbox)

        vbox.addWidget(QLabel(_("Address") + ":"))
        self.addr_e = ButtonsLineEdit(self.address)
        self.addr_e.addCopyButton(self.app)
        icon = "qrcode_white.png" if ColorScheme.dark_scheme else "qrcode.png"
        self.addr_e.addButton(icon, self.show_qr, _("Show QR Code"))
        self.addr_e.setReadOnly(True)
        vbox.addWidget(self.addr_e)

        try:
            pubkeys = self.wallet.get_public_keys(address)
        except BaseException as e:
            pubkeys = None
        if pubkeys:
            vbox.addWidget(QLabel(_("Public keys") + ':'))
            for pubkey in pubkeys:
                pubkey_e = ButtonsLineEdit(pubkey)
                pubkey_e.addCopyButton(self.app)
                pubkey_e.setReadOnly(True)
                vbox.addWidget(pubkey_e)

        redeem_script = self.wallet.get_redeem_script(address)
        if redeem_script:
            vbox.addWidget(QLabel(_("Redeem Script") + ':'))
            redeem_e = ShowQRTextEdit(text=redeem_script)
            redeem_e.addCopyButton(self.app)
            vbox.addWidget(redeem_e)

        witness_script = self.wallet.get_witness_script(address)
        if witness_script:
            vbox.addWidget(QLabel(_("Witness Script") + ':'))
            witness_e = ShowQRTextEdit(text=witness_script)
            witness_e.addCopyButton(self.app)
            vbox.addWidget(witness_e)

        address_path_str = self.wallet.get_address_path_str(address)
        if address_path_str:
            vbox.addWidget(QLabel(_("Derivation path") + ':'))
            der_path_e = ButtonsLineEdit(address_path_str)
            der_path_e.addCopyButton(self.app)
            der_path_e.setReadOnly(True)
            vbox.addWidget(der_path_e)

        vbox.addWidget(QLabel(_("History")))
        addr_hist_model = AddressHistoryModel(self.parent, self.address)
        self.hw = HistoryList(self.parent, addr_hist_model)
        addr_hist_model.set_view(self.hw)
        vbox.addWidget(self.hw)

        vbox.addLayout(Buttons(CloseButton(self)))
        self.format_amount = self.parent.format_amount
        addr_hist_model.refresh('address dialog constructor')

    def show_qr(self):
        text = self.address
        try:
            self.parent.show_qrcode(text, 'Address', parent=self)
        except Exception as e:
            self.show_message(repr(e))
