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

import sys
import copy
import datetime
import traceback
import time
from typing import TYPE_CHECKING, Callable, Optional, List
from functools import partial
from decimal import Decimal

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QTextCharFormat, QBrush, QFont, QPixmap
from PyQt5.QtWidgets import (QDialog, QLabel, QPushButton, QHBoxLayout, QVBoxLayout, QWidget, QGridLayout,
                             QTextEdit, QFrame, QAction, QToolButton, QMenu, QCheckBox)
import qrcode
from qrcode import exceptions

from electrum.simple_config import SimpleConfig
from electrum.util import quantize_feerate
from electrum.bitcoin import base_encode, NLOCKTIME_BLOCKHEIGHT_MAX
from electrum.i18n import _
from electrum.plugin import run_hook
from electrum import simple_config
from electrum.transaction import SerializationError, Transaction, PartialTransaction, PartialTxInput
from electrum.logging import get_logger

from .util import (MessageBoxMixin, read_QIcon, Buttons, icon_path,
                   MONOSPACE_FONT, ColorScheme, ButtonsLineEdit, text_dialog,
                   char_width_in_lineedit, TRANSACTION_FILE_EXTENSION_FILTER_SEPARATE,
                   TRANSACTION_FILE_EXTENSION_FILTER_ONLY_COMPLETE_TX,
                   TRANSACTION_FILE_EXTENSION_FILTER_ONLY_PARTIAL_TX,
                   BlockingWaitingDialog)

from .fee_slider import FeeSlider, FeeComboBox
from .confirm_tx_dialog import TxEditor
from .amountedit import FeerateEdit, BTCAmountEdit
from .locktimeedit import LockTimeEdit

if TYPE_CHECKING:
    from .main_window import ElectrumWindow


class TxSizeLabel(QLabel):
    def setAmount(self, byte_size):
        self.setText(('x   %s bytes   =' % byte_size) if byte_size else '')


class QTextEditWithDefaultSize(QTextEdit):
    def sizeHint(self):
        return QSize(0, 100)



_logger = get_logger(__name__)
dialogs = []  # Otherwise python randomly garbage collects the dialogs...


def show_transaction(tx: Transaction, *, parent: 'ElectrumWindow', desc=None, prompt_if_unsaved=False):
    try:
        d = TxDialog(tx, parent=parent, desc=desc, prompt_if_unsaved=prompt_if_unsaved)
    except SerializationError as e:
        _logger.exception('unable to deserialize the transaction')
        parent.show_critical(_("Electrum was unable to deserialize the transaction:") + "\n" + str(e))
    else:
        d.show()



class BaseTxDialog(QDialog, MessageBoxMixin):

    def __init__(self, *, parent: 'ElectrumWindow', desc, prompt_if_unsaved, finalized: bool, external_keypairs=None):
        '''Transactions in the wallet will show their description.
        Pass desc to give a description for txs not yet in the wallet.
        '''
        # We want to be a top-level window
        QDialog.__init__(self, parent=None)
        self.tx = None  # type: Optional[Transaction]
        self.external_keypairs = external_keypairs
        self.finalized = finalized
        self.main_window = parent
        self.config = parent.config
        self.wallet = parent.wallet
        self.prompt_if_unsaved = prompt_if_unsaved
        self.saved = False
        self.desc = desc
        self.setMinimumWidth(950)
        self.set_title()

        self.psbt_only_widgets = []  # type: List[QWidget]

        vbox = QVBoxLayout()
        self.setLayout(vbox)

        vbox.addWidget(QLabel(_("Transaction ID:")))
        self.tx_hash_e  = ButtonsLineEdit()
        qr_show = lambda: parent.show_qrcode(str(self.tx_hash_e.text()), 'Transaction ID', parent=self)
        qr_icon = "qrcode_white.png" if ColorScheme.dark_scheme else "qrcode.png"
        self.tx_hash_e.addButton(qr_icon, qr_show, _("Show as QR code"))
        self.tx_hash_e.setReadOnly(True)
        vbox.addWidget(self.tx_hash_e)

        self.add_tx_stats(vbox)

        vbox.addSpacing(10)

        self.inputs_header = QLabel()
        vbox.addWidget(self.inputs_header)
        self.inputs_textedit = QTextEditWithDefaultSize()
        vbox.addWidget(self.inputs_textedit)
        self.outputs_header = QLabel()
        vbox.addWidget(self.outputs_header)
        self.outputs_textedit = QTextEditWithDefaultSize()
        vbox.addWidget(self.outputs_textedit)
        self.sign_button = b = QPushButton(_("Sign"))
        b.clicked.connect(self.sign)

        self.broadcast_button = b = QPushButton(_("Broadcast"))
        b.clicked.connect(self.do_broadcast)

        self.save_button = b = QPushButton(_("Save"))
        b.clicked.connect(self.save)

        self.cancel_button = b = QPushButton(_("Close"))
        b.clicked.connect(self.close)
        b.setDefault(True)

        self.export_actions_menu = export_actions_menu = QMenu()
        self.add_export_actions_to_menu(export_actions_menu)
        export_actions_menu.addSeparator()
        export_submenu = export_actions_menu.addMenu(_("For CoinJoin; strip privates"))
        self.add_export_actions_to_menu(export_submenu, gettx=self._gettx_for_coinjoin)
        self.psbt_only_widgets.append(export_submenu)
        export_submenu = export_actions_menu.addMenu(_("For hardware device; include xpubs"))
        self.add_export_actions_to_menu(export_submenu, gettx=self._gettx_for_hardware_device)
        self.psbt_only_widgets.append(export_submenu)

        self.export_actions_button = QToolButton()
        self.export_actions_button.setText(_("Export"))
        self.export_actions_button.setMenu(export_actions_menu)
        self.export_actions_button.setPopupMode(QToolButton.InstantPopup)

        self.finalize_button = QPushButton(_('Finalize'))
        self.finalize_button.clicked.connect(self.on_finalize)

        partial_tx_actions_menu = QMenu()
        ptx_merge_sigs_action = QAction(_("Merge signatures from"), self)
        ptx_merge_sigs_action.triggered.connect(self.merge_sigs)
        partial_tx_actions_menu.addAction(ptx_merge_sigs_action)
        self._ptx_join_txs_action = QAction(_("Join inputs/outputs"), self)
        self._ptx_join_txs_action.triggered.connect(self.join_tx_with_another)
        partial_tx_actions_menu.addAction(self._ptx_join_txs_action)
        self.partial_tx_actions_button = QToolButton()
        self.partial_tx_actions_button.setText(_("Combine"))
        self.partial_tx_actions_button.setMenu(partial_tx_actions_menu)
        self.partial_tx_actions_button.setPopupMode(QToolButton.InstantPopup)
        self.psbt_only_widgets.append(self.partial_tx_actions_button)

        # Action buttons
        self.buttons = [self.partial_tx_actions_button, self.sign_button, self.broadcast_button, self.cancel_button]
        # Transaction sharing buttons
        self.sharing_buttons = [self.finalize_button, self.export_actions_button, self.save_button]
        run_hook('transaction_dialog', self)
        if not self.finalized:
            self.create_fee_controls()
            vbox.addWidget(self.feecontrol_fields)
        self.hbox = hbox = QHBoxLayout()
        hbox.addLayout(Buttons(*self.sharing_buttons))
        hbox.addStretch(1)
        hbox.addLayout(Buttons(*self.buttons))
        vbox.addLayout(hbox)
        self.set_buttons_visibility()

        dialogs.append(self)

    def set_buttons_visibility(self):
        for b in [self.export_actions_button, self.save_button, self.sign_button, self.broadcast_button, self.partial_tx_actions_button]:
            b.setVisible(self.finalized)
        for b in [self.finalize_button]:
            b.setVisible(not self.finalized)

    def set_tx(self, tx: 'Transaction'):
        # Take a copy; it might get updated in the main window by
        # e.g. the FX plugin.  If this happens during or after a long
        # sign operation the signatures are lost.
        self.tx = tx = copy.deepcopy(tx)
        try:
            self.tx.deserialize()
        except BaseException as e:
            raise SerializationError(e)
        # If the wallet can populate the inputs with more info, do it now.
        # As a result, e.g. we might learn an imported address tx is segwit,
        # or that a beyond-gap-limit address is is_mine.
        # note: this might fetch prev txs over the network.
        tx.add_info_from_wallet(self.wallet)

    def do_broadcast(self):
        self.main_window.push_top_level_window(self)
        try:
            self.main_window.broadcast_transaction(self.tx)
        finally:
            self.main_window.pop_top_level_window(self)
        self.saved = True
        self.update()

    def closeEvent(self, event):
        if (self.prompt_if_unsaved and not self.saved
                and not self.question(_('This transaction is not saved. Close anyway?'), title=_("Warning"))):
            event.ignore()
        else:
            event.accept()
            try:
                dialogs.remove(self)
            except ValueError:
                pass  # was not in list already

    def reject(self):
        # Override escape-key to close normally (and invoke closeEvent)
        self.close()

    def add_export_actions_to_menu(self, menu: QMenu, *, gettx: Callable[[], Transaction] = None) -> None:
        if gettx is None:
            gettx = lambda: None

        action = QAction(_("Copy to clipboard"), self)
        action.triggered.connect(lambda: self.copy_to_clipboard(tx=gettx()))
        menu.addAction(action)

        qr_icon = "qrcode_white.png" if ColorScheme.dark_scheme else "qrcode.png"
        action = QAction(read_QIcon(qr_icon), _("Show as QR code"), self)
        action.triggered.connect(lambda: self.show_qr(tx=gettx()))
        menu.addAction(action)

        action = QAction(_("Export to file"), self)
        action.triggered.connect(lambda: self.export_to_file(tx=gettx()))
        menu.addAction(action)

    def _gettx_for_coinjoin(self) -> PartialTransaction:
        if not isinstance(self.tx, PartialTransaction):
            raise Exception("Can only export partial transactions for coinjoins.")
        tx = copy.deepcopy(self.tx)
        tx.prepare_for_export_for_coinjoin()
        return tx

    def _gettx_for_hardware_device(self) -> PartialTransaction:
        if not isinstance(self.tx, PartialTransaction):
            raise Exception("Can only export partial transactions for hardware device.")
        tx = copy.deepcopy(self.tx)
        tx.add_info_from_wallet(self.wallet, include_xpubs_and_full_paths=True)
        # log warning if PSBT_*_BIP32_DERIVATION fields cannot be filled with full path due to missing info
        from electrum.keystore import Xpub
        def is_ks_missing_info(ks):
            return (isinstance(ks, Xpub) and (ks.get_root_fingerprint() is None
                                              or ks.get_derivation_prefix() is None))
        if any([is_ks_missing_info(ks) for ks in self.wallet.get_keystores()]):
            _logger.warning('PSBT was requested to be filled with full bip32 paths but '
                            'some keystores lacked either the derivation prefix or the root fingerprint')
        return tx

    def copy_to_clipboard(self, *, tx: Transaction = None):
        if tx is None:
            tx = self.tx
        self.main_window.do_copy(str(tx), title=_("Transaction"))

    def show_qr(self, *, tx: Transaction = None):
        if tx is None:
            tx = self.tx
        qr_data = tx.to_qr_data()
        try:
            self.main_window.show_qrcode(qr_data, 'Transaction', parent=self)
        except qrcode.exceptions.DataOverflowError:
            self.show_error(_('Failed to display QR code.') + '\n' +
                            _('Transaction is too large in size.'))
        except Exception as e:
            self.show_error(_('Failed to display QR code.') + '\n' + repr(e))

    def sign(self):
        def sign_done(success):
            if self.tx.is_complete():
                self.prompt_if_unsaved = True
                self.saved = False
            self.update()
            self.main_window.pop_top_level_window(self)

        self.sign_button.setDisabled(True)
        self.main_window.push_top_level_window(self)
        self.main_window.sign_tx(self.tx, callback=sign_done, external_keypairs=self.external_keypairs)

    def save(self):
        self.main_window.push_top_level_window(self)
        if self.main_window.save_transaction_into_wallet(self.tx):
            self.save_button.setDisabled(True)
            self.saved = True
        self.main_window.pop_top_level_window(self)

    def export_to_file(self, *, tx: Transaction = None):
        if tx is None:
            tx = self.tx
        if isinstance(tx, PartialTransaction):
            tx.finalize_psbt()
        if tx.is_complete():
            name = 'signed_%s' % (tx.txid()[0:8])
            extension = 'txn'
            default_filter = TRANSACTION_FILE_EXTENSION_FILTER_ONLY_COMPLETE_TX
        else:
            name = self.wallet.basename() + time.strftime('-%Y%m%d-%H%M')
            extension = 'psbt'
            default_filter = TRANSACTION_FILE_EXTENSION_FILTER_ONLY_PARTIAL_TX
        name = f'{name}.{extension}'
        fileName = self.main_window.getSaveFileName(_("Select where to save your transaction"),
                                                    name,
                                                    TRANSACTION_FILE_EXTENSION_FILTER_SEPARATE,
                                                    default_extension=extension,
                                                    default_filter=default_filter)
        if not fileName:
            return
        if tx.is_complete():  # network tx hex
            with open(fileName, "w+") as f:
                network_tx_hex = tx.serialize_to_network()
                f.write(network_tx_hex + '\n')
        else:  # if partial: PSBT bytes
            assert isinstance(tx, PartialTransaction)
            with open(fileName, "wb+") as f:
                f.write(tx.serialize_as_bytes())

        self.show_message(_("Transaction exported successfully"))
        self.saved = True

    def merge_sigs(self):
        if not isinstance(self.tx, PartialTransaction):
            return
        text = text_dialog(self, _('Input raw transaction'),
                           _("Transaction to merge signatures from") + ":",
                           _("Load transaction"))
        if not text:
            return
        tx = self.main_window.tx_from_text(text)
        if not tx:
            return
        try:
            self.tx.combine_with_other_psbt(tx)
        except Exception as e:
            self.show_error(_("Error combining partial transactions") + ":\n" + repr(e))
            return
        self.update()

    def join_tx_with_another(self):
        if not isinstance(self.tx, PartialTransaction):
            return
        text = text_dialog(self, _('Input raw transaction'),
                           _("Transaction to join with") + " (" + _("add inputs and outputs") + "):",
                           _("Load transaction"))
        if not text:
            return
        tx = self.main_window.tx_from_text(text)
        if not tx:
            return
        try:
            self.tx.join_with_other_psbt(tx)
        except Exception as e:
            self.show_error(_("Error joining partial transactions") + ":\n" + repr(e))
            return
        self.update()

    def update(self):
        if not self.finalized:
            self.update_fee_fields()
            self.finalize_button.setEnabled(self.can_finalize())
        if self.tx is None:
            return
        self.update_io()
        desc = self.desc
        base_unit = self.main_window.base_unit()
        format_amount = self.main_window.format_amount
        tx_details = self.wallet.get_tx_info(self.tx)
        tx_mined_status = tx_details.tx_mined_status
        exp_n = tx_details.mempool_depth_bytes
        amount, fee = tx_details.amount, tx_details.fee
        size = self.tx.estimated_size()
        txid = self.tx.txid()
        lnworker_history = self.wallet.lnworker.get_onchain_history() if self.wallet.lnworker else {}
        if txid in lnworker_history:
            item = lnworker_history[txid]
            ln_amount = item['amount_msat'] / 1000
            if amount is None:
                tx_mined_status = self.wallet.lnworker.lnwatcher.get_tx_height(txid)
        else:
            ln_amount = None
        self.broadcast_button.setEnabled(tx_details.can_broadcast)
        can_sign = not self.tx.is_complete() and \
            (self.wallet.can_sign(self.tx) or bool(self.external_keypairs))
        self.sign_button.setEnabled(can_sign)
        if self.finalized and tx_details.txid:
            self.tx_hash_e.setText(tx_details.txid)
        else:
            # note: when not finalized, RBF and locktime changes do not trigger
            #       a make_tx, so the txid is unreliable, hence:
            self.tx_hash_e.setText(_('Unknown'))
        if not desc:
            self.tx_desc.hide()
        else:
            self.tx_desc.setText(_("Description") + ': ' + desc)
            self.tx_desc.show()
        self.status_label.setText(_('Status:') + ' ' + tx_details.status)

        if tx_mined_status.timestamp:
            time_str = datetime.datetime.fromtimestamp(tx_mined_status.timestamp).isoformat(' ')[:-3]
            self.date_label.setText(_("Date: {}").format(time_str))
            self.date_label.show()
        elif exp_n is not None:
            text = '%.2f MB'%(exp_n/1000000)
            self.date_label.setText(_('Position in mempool: {} from tip').format(text))
            self.date_label.show()
        else:
            self.date_label.hide()
        if self.tx.locktime <= NLOCKTIME_BLOCKHEIGHT_MAX:
            locktime_final_str = f"LockTime: {self.tx.locktime} (height)"
        else:
            locktime_final_str = f"LockTime: {self.tx.locktime} ({datetime.datetime.fromtimestamp(self.tx.locktime)})"
        self.locktime_final_label.setText(locktime_final_str)
        if self.locktime_e.get_locktime() is None:
            self.locktime_e.set_locktime(self.tx.locktime)
        self.rbf_label.setText(_('Replace by fee') + f": {not self.tx.is_final()}")

        if tx_mined_status.header_hash:
            self.block_hash_label.setText(_("Included in block: {}")
                                          .format(tx_mined_status.header_hash))
            self.block_height_label.setText(_("At block height: {}")
                                            .format(tx_mined_status.height))
        else:
            self.block_hash_label.hide()
            self.block_height_label.hide()
        if amount is None and ln_amount is None:
            amount_str = _("Transaction unrelated to your wallet")
        elif amount is None:
            amount_str = ''
        elif amount > 0:
            amount_str = _("Amount received:") + ' %s'% format_amount(amount) + ' ' + base_unit
        else:
            amount_str = _("Amount sent:") + ' %s'% format_amount(-amount) + ' ' + base_unit
        if amount_str:
            self.amount_label.setText(amount_str)
        else:
            self.amount_label.hide()
        size_str = _("Size:") + ' %d bytes'% size
        fee_str = _("Fee") + ': %s' % (format_amount(fee) + ' ' + base_unit if fee is not None else _('unknown'))
        if fee is not None:
            fee_rate = fee/size*1000
            fee_str += '  ( %s ) ' % self.main_window.format_fee_rate(fee_rate)
            feerate_warning = simple_config.FEERATE_WARNING_HIGH_FEE
            if fee_rate > feerate_warning:
                fee_str += ' - ' + _('Warning') + ': ' + _("high fee") + '!'
        if isinstance(self.tx, PartialTransaction):
            risk_of_burning_coins = (can_sign and fee is not None
                                     and self.wallet.get_warning_for_risk_of_burning_coins_as_fees(self.tx))
            self.fee_warning_icon.setToolTip(str(risk_of_burning_coins))
            self.fee_warning_icon.setVisible(bool(risk_of_burning_coins))
        self.fee_label.setText(fee_str)
        self.size_label.setText(size_str)
        if ln_amount is None or ln_amount == 0:
            ln_amount_str = ''
        elif ln_amount > 0:
            ln_amount_str = _('Amount received in channels') + ': ' + format_amount(ln_amount) + ' ' + base_unit
        elif ln_amount < 0:
            ln_amount_str = _('Amount withdrawn from channels') + ': ' + format_amount(-ln_amount) + ' ' + base_unit
        if ln_amount_str:
            self.ln_amount_label.setText(ln_amount_str)
        else:
            self.ln_amount_label.hide()
        show_psbt_only_widgets = self.finalized and isinstance(self.tx, PartialTransaction)
        for widget in self.psbt_only_widgets:
            if isinstance(widget, QMenu):
                widget.menuAction().setVisible(show_psbt_only_widgets)
            else:
                widget.setVisible(show_psbt_only_widgets)
        if tx_details.is_lightning_funding_tx:
            self._ptx_join_txs_action.setEnabled(False)  # would change txid

        self.save_button.setEnabled(tx_details.can_save_as_local)
        if tx_details.can_save_as_local:
            self.save_button.setToolTip(_("Save transaction offline"))
        else:
            self.save_button.setToolTip(_("Transaction already saved or not yet signed."))

        run_hook('transaction_dialog_update', self)

    def update_io(self):
        inputs_header_text = _("Inputs") + ' (%d)'%len(self.tx.inputs())
        if not self.finalized:
            selected_coins = self.main_window.get_manually_selected_coins()
            if selected_coins is not None:
                inputs_header_text += f"  -  " + _("Coin selection active ({} UTXOs selected)").format(len(selected_coins))
        self.inputs_header.setText(inputs_header_text)
        ext = QTextCharFormat()
        rec = QTextCharFormat()
        rec.setBackground(QBrush(ColorScheme.GREEN.as_color(background=True)))
        rec.setToolTip(_("Wallet receive address"))
        chg = QTextCharFormat()
        chg.setBackground(QBrush(ColorScheme.YELLOW.as_color(background=True)))
        chg.setToolTip(_("Wallet change address"))
        twofactor = QTextCharFormat()
        twofactor.setBackground(QBrush(ColorScheme.BLUE.as_color(background=True)))
        twofactor.setToolTip(_("TrustedCoin (2FA) fee for the next batch of transactions"))

        def text_format(addr):
            if self.wallet.is_mine(addr):
                return chg if self.wallet.is_change(addr) else rec
            elif self.wallet.is_billing_address(addr):
                return twofactor
            return ext

        def format_amount(amt):
            return self.main_window.format_amount(amt, whitespaces=True)

        i_text = self.inputs_textedit
        i_text.clear()
        i_text.setFont(QFont(MONOSPACE_FONT))
        i_text.setReadOnly(True)
        cursor = i_text.textCursor()
        for txin in self.tx.inputs():
            if txin.is_coinbase_input():
                cursor.insertText('coinbase')
            else:
                prevout_hash = txin.prevout.txid.hex()
                prevout_n = txin.prevout.out_idx
                cursor.insertText(prevout_hash + ":%-4d " % prevout_n, ext)
                addr = self.wallet.get_txin_address(txin)
                if addr is None:
                    addr = ''
                cursor.insertText(addr, text_format(addr))
                txin_value = self.wallet.get_txin_value(txin)
                if txin_value is not None:
                    cursor.insertText(format_amount(txin_value), ext)
            cursor.insertBlock()

        self.outputs_header.setText(_("Outputs") + ' (%d)'%len(self.tx.outputs()))
        o_text = self.outputs_textedit
        o_text.clear()
        o_text.setFont(QFont(MONOSPACE_FONT))
        o_text.setReadOnly(True)
        cursor = o_text.textCursor()
        for o in self.tx.outputs():
            addr, v = o.get_ui_address_str(), o.value
            cursor.insertText(addr, text_format(addr))
            if v is not None:
                cursor.insertText('\t', ext)
                cursor.insertText(format_amount(v), ext)
            cursor.insertBlock()

    def add_tx_stats(self, vbox):
        hbox_stats = QHBoxLayout()

        # left column
        vbox_left = QVBoxLayout()
        self.tx_desc = TxDetailLabel(word_wrap=True)
        vbox_left.addWidget(self.tx_desc)
        self.status_label = TxDetailLabel()
        vbox_left.addWidget(self.status_label)
        self.date_label = TxDetailLabel()
        vbox_left.addWidget(self.date_label)
        self.amount_label = TxDetailLabel()
        vbox_left.addWidget(self.amount_label)
        self.ln_amount_label = TxDetailLabel()
        vbox_left.addWidget(self.ln_amount_label)

        fee_hbox = QHBoxLayout()
        self.fee_label = TxDetailLabel()
        fee_hbox.addWidget(self.fee_label)
        self.fee_warning_icon = QLabel()
        pixmap = QPixmap(icon_path("warning"))
        pixmap_size = round(2 * char_width_in_lineedit())
        pixmap = pixmap.scaled(pixmap_size, pixmap_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.fee_warning_icon.setPixmap(pixmap)
        self.fee_warning_icon.setVisible(False)
        fee_hbox.addWidget(self.fee_warning_icon)
        fee_hbox.addStretch(1)
        vbox_left.addLayout(fee_hbox)

        vbox_left.addStretch(1)
        hbox_stats.addLayout(vbox_left, 50)

        # vertical line separator
        line_separator = QFrame()
        line_separator.setFrameShape(QFrame.VLine)
        line_separator.setFrameShadow(QFrame.Sunken)
        line_separator.setLineWidth(1)
        hbox_stats.addWidget(line_separator)

        # right column
        vbox_right = QVBoxLayout()
        self.size_label = TxDetailLabel()
        vbox_right.addWidget(self.size_label)
        self.rbf_label = TxDetailLabel()
        vbox_right.addWidget(self.rbf_label)
        self.rbf_cb = QCheckBox(_('Replace by fee'))
        self.rbf_cb.setChecked(bool(self.config.get('use_rbf', True)))
        vbox_right.addWidget(self.rbf_cb)

        self.locktime_final_label = TxDetailLabel()
        vbox_right.addWidget(self.locktime_final_label)

        locktime_setter_hbox = QHBoxLayout()
        locktime_setter_hbox.setContentsMargins(0, 0, 0, 0)
        locktime_setter_hbox.setSpacing(0)
        locktime_setter_label = TxDetailLabel()
        locktime_setter_label.setText("LockTime: ")
        self.locktime_e = LockTimeEdit()
        locktime_setter_hbox.addWidget(locktime_setter_label)
        locktime_setter_hbox.addWidget(self.locktime_e)
        locktime_setter_hbox.addStretch(1)
        self.locktime_setter_widget = QWidget()
        self.locktime_setter_widget.setLayout(locktime_setter_hbox)
        vbox_right.addWidget(self.locktime_setter_widget)

        self.block_height_label = TxDetailLabel()
        vbox_right.addWidget(self.block_height_label)
        vbox_right.addStretch(1)
        hbox_stats.addLayout(vbox_right, 50)

        vbox.addLayout(hbox_stats)

        # below columns
        self.block_hash_label = TxDetailLabel(word_wrap=True)
        vbox.addWidget(self.block_hash_label)

        # set visibility after parenting can be determined by Qt
        self.rbf_label.setVisible(self.finalized)
        self.rbf_cb.setVisible(not self.finalized)
        self.locktime_final_label.setVisible(self.finalized)
        self.locktime_setter_widget.setVisible(not self.finalized)

    def set_title(self):
        self.setWindowTitle(_("Create transaction") if not self.finalized else _("Transaction"))

    def can_finalize(self) -> bool:
        return False

    def on_finalize(self):
        pass  # overridden in subclass

    def update_fee_fields(self):
        pass  # overridden in subclass


class TxDetailLabel(QLabel):
    def __init__(self, *, word_wrap=None):
        super().__init__()
        self.setTextInteractionFlags(Qt.TextSelectableByMouse)
        if word_wrap is not None:
            self.setWordWrap(word_wrap)


class TxDialog(BaseTxDialog):
    def __init__(self, tx: Transaction, *, parent: 'ElectrumWindow', desc, prompt_if_unsaved):
        BaseTxDialog.__init__(self, parent=parent, desc=desc, prompt_if_unsaved=prompt_if_unsaved, finalized=True)
        self.set_tx(tx)
        self.update()



class PreviewTxDialog(BaseTxDialog, TxEditor):

    def __init__(self, *, make_tx, external_keypairs, window: 'ElectrumWindow'):
        TxEditor.__init__(self, window=window, make_tx=make_tx, is_sweep=bool(external_keypairs))
        BaseTxDialog.__init__(self, parent=window, desc='', prompt_if_unsaved=False,
                              finalized=False, external_keypairs=external_keypairs)
        BlockingWaitingDialog(window, _("Preparing transaction..."),
                              lambda: self.update_tx(fallback_to_zero_fee=True))
        self.update()

    def create_fee_controls(self):

        self.size_e = TxSizeLabel()
        self.size_e.setAlignment(Qt.AlignCenter)
        self.size_e.setAmount(0)
        self.size_e.setStyleSheet(ColorScheme.DEFAULT.as_stylesheet())

        self.feerate_e = FeerateEdit(lambda: 0)
        self.feerate_e.setAmount(self.config.fee_per_byte())
        self.feerate_e.textEdited.connect(partial(self.on_fee_or_feerate, self.feerate_e, False))
        self.feerate_e.editingFinished.connect(partial(self.on_fee_or_feerate, self.feerate_e, True))

        self.fee_e = BTCAmountEdit(self.main_window.get_decimal_point)
        self.fee_e.textEdited.connect(partial(self.on_fee_or_feerate, self.fee_e, False))
        self.fee_e.editingFinished.connect(partial(self.on_fee_or_feerate, self.fee_e, True))

        self.fee_e.textChanged.connect(self.entry_changed)
        self.feerate_e.textChanged.connect(self.entry_changed)

        self.fee_slider = FeeSlider(self, self.config, self.fee_slider_callback)
        self.fee_combo = FeeComboBox(self.fee_slider)
        self.fee_slider.setFixedWidth(self.fee_e.width())

        def feerounding_onclick():
            text = (self.feerounding_text + '\n\n' +
                    _('To somewhat protect your privacy, Electrum tries to create change with similar precision to other outputs.') + ' ' +
                    _('At most 100 satoshis might be lost due to this rounding.') + ' ' +
                    _("You can disable this setting in '{}'.").format(_('Preferences')) + '\n' +
                    _('Also, dust is not kept as change, but added to the fee.')  + '\n' +
                    _('Also, when batching RBF transactions, BIP 125 imposes a lower bound on the fee.'))
            self.show_message(title=_('Fee rounding'), msg=text)

        self.feerounding_icon = QToolButton()
        self.feerounding_icon.setIcon(read_QIcon('info.png'))
        self.feerounding_icon.setAutoRaise(True)
        self.feerounding_icon.clicked.connect(feerounding_onclick)
        self.feerounding_icon.setVisible(False)

        self.feecontrol_fields = QWidget()
        hbox = QHBoxLayout(self.feecontrol_fields)
        hbox.setContentsMargins(0, 0, 0, 0)
        grid = QGridLayout()
        grid.addWidget(QLabel(_("Target fee:")), 0, 0)
        grid.addWidget(self.feerate_e, 0, 1)
        grid.addWidget(self.size_e, 0, 2)
        grid.addWidget(self.fee_e, 0, 3)
        grid.addWidget(self.feerounding_icon, 0, 4)
        grid.addWidget(self.fee_slider, 1, 1)
        grid.addWidget(self.fee_combo, 1, 2)
        hbox.addLayout(grid)
        hbox.addStretch(1)

    def fee_slider_callback(self, dyn, pos, fee_rate):
        super().fee_slider_callback(dyn, pos, fee_rate)
        self.fee_slider.activate()
        if fee_rate:
            fee_rate = Decimal(fee_rate)
            self.feerate_e.setAmount(quantize_feerate(fee_rate / 1000))
        else:
            self.feerate_e.setAmount(None)
        self.fee_e.setModified(False)

    def on_fee_or_feerate(self, edit_changed, editing_finished):
        edit_other = self.feerate_e if edit_changed == self.fee_e else self.fee_e
        if editing_finished:
            if edit_changed.get_amount() is None:
                # This is so that when the user blanks the fee and moves on,
                # we go back to auto-calculate mode and put a fee back.
                edit_changed.setModified(False)
        else:
            # edit_changed was edited just now, so make sure we will
            # freeze the correct fee setting (this)
            edit_other.setModified(False)
        self.fee_slider.deactivate()
        self.update()

    def is_send_fee_frozen(self):
        return self.fee_e.isVisible() and self.fee_e.isModified() \
               and (self.fee_e.text() or self.fee_e.hasFocus())

    def is_send_feerate_frozen(self):
        return self.feerate_e.isVisible() and self.feerate_e.isModified() \
               and (self.feerate_e.text() or self.feerate_e.hasFocus())

    def set_feerounding_text(self, num_satoshis_added):
        self.feerounding_text = (_('Additional {} satoshis are going to be added.')
                                 .format(num_satoshis_added))

    def get_fee_estimator(self):
        if self.is_send_fee_frozen() and self.fee_e.get_amount() is not None:
            fee_estimator = self.fee_e.get_amount()
        elif self.is_send_feerate_frozen() and self.feerate_e.get_amount() is not None:
            amount = self.feerate_e.get_amount()  # sat/byte feerate
            amount = 0 if amount is None else amount * 1000  # sat/kilobyte feerate
            fee_estimator = partial(
                SimpleConfig.estimate_fee_for_feerate, amount)
        else:
            fee_estimator = None
        return fee_estimator

    def entry_changed(self):
        # blue color denotes auto-filled values
        text = ""
        fee_color = ColorScheme.DEFAULT
        feerate_color = ColorScheme.DEFAULT
        if self.not_enough_funds:
            fee_color = ColorScheme.RED
            feerate_color = ColorScheme.RED
        elif self.fee_e.isModified():
            feerate_color = ColorScheme.BLUE
        elif self.feerate_e.isModified():
            fee_color = ColorScheme.BLUE
        else:
            fee_color = ColorScheme.BLUE
            feerate_color = ColorScheme.BLUE
        self.fee_e.setStyleSheet(fee_color.as_stylesheet())
        self.feerate_e.setStyleSheet(feerate_color.as_stylesheet())
        #
        self.needs_update = True

    def update_fee_fields(self):
        freeze_fee = self.is_send_fee_frozen()
        freeze_feerate = self.is_send_feerate_frozen()
        if self.no_dynfee_estimates:
            size = self.tx.estimated_size()
            self.size_e.setAmount(size)
        if self.not_enough_funds or self.no_dynfee_estimates:
            if not freeze_fee:
                self.fee_e.setAmount(None)
            if not freeze_feerate:
                self.feerate_e.setAmount(None)
            self.feerounding_icon.setVisible(False)
            return

        tx = self.tx
        size = tx.estimated_size()
        fee = tx.get_fee()

        self.size_e.setAmount(size)

        # Displayed fee/fee_rate values are set according to user input.
        # Due to rounding or dropping dust in CoinChooser,
        # actual fees often differ somewhat.
        if freeze_feerate or self.fee_slider.is_active():
            displayed_feerate = self.feerate_e.get_amount()
            if displayed_feerate is not None:
                displayed_feerate = quantize_feerate(displayed_feerate)
            elif self.fee_slider.is_active():
                # fallback to actual fee
                displayed_feerate = quantize_feerate(fee / size) if fee is not None else None
                self.feerate_e.setAmount(displayed_feerate)
            displayed_fee = round(displayed_feerate * size) if displayed_feerate is not None else None
            self.fee_e.setAmount(displayed_fee)
        else:
            if freeze_fee:
                displayed_fee = self.fee_e.get_amount()
            else:
                # fallback to actual fee if nothing is frozen
                displayed_fee = fee
                self.fee_e.setAmount(displayed_fee)
            displayed_fee = displayed_fee if displayed_fee else 0
            displayed_feerate = quantize_feerate(displayed_fee / size) if displayed_fee is not None else None
            self.feerate_e.setAmount(displayed_feerate)

        # show/hide fee rounding icon
        feerounding = (fee - displayed_fee) if (fee and displayed_fee is not None) else 0
        self.set_feerounding_text(int(feerounding))
        self.feerounding_icon.setToolTip(self.feerounding_text)
        self.feerounding_icon.setVisible(abs(feerounding) >= 1)

    def can_finalize(self):
        return (self.tx is not None
                and not self.not_enough_funds)

    def on_finalize(self):
        if not self.can_finalize():
            return
        assert self.tx
        self.finalized = True
        self.tx.set_rbf(self.rbf_cb.isChecked())
        locktime = self.locktime_e.get_locktime()
        if locktime is not None:
            self.tx.locktime = locktime
        for widget in [self.fee_slider, self.fee_combo, self.feecontrol_fields, self.rbf_cb,
                       self.locktime_setter_widget, self.locktime_e]:
            widget.setEnabled(False)
            widget.setVisible(False)
        for widget in [self.rbf_label, self.locktime_final_label]:
            widget.setVisible(True)
        self.set_title()
        self.set_buttons_visibility()
        self.update()
