import copy
from datetime import datetime
from typing import NamedTuple, Callable, TYPE_CHECKING

from kivy.app import App
from kivy.factory import Factory
from kivy.properties import ObjectProperty
from kivy.lang import Builder
from kivy.clock import Clock
from kivy.uix.label import Label
from kivy.uix.dropdown import DropDown
from kivy.uix.button import Button

from .question import Question
from electrum.gui.kivy.i18n import _

from electrum.util import InvalidPassword
from electrum.address_synchronizer import TX_HEIGHT_LOCAL
from electrum.wallet import CannotBumpFee, CannotDoubleSpendTx
from electrum.transaction import Transaction, PartialTransaction
from ...util import address_colors

if TYPE_CHECKING:
    from ...main_window import ElectrumWindow


Builder.load_string('''

<TxDialog>
    id: popup
    title: _('Transaction')
    is_mine: True
    can_sign: False
    can_broadcast: False
    can_rbf: False
    fee_str: ''
    feerate_str: ''
    date_str: ''
    date_label:''
    amount_str: ''
    tx_hash: ''
    status_str: ''
    description: ''
    outputs_str: ''
    BoxLayout:
        orientation: 'vertical'
        ScrollView:
            scroll_type: ['bars', 'content']
            bar_width: '25dp'
            GridLayout:
                height: self.minimum_height
                size_hint_y: None
                cols: 1
                spacing: '10dp'
                padding: '10dp'
                GridLayout:
                    height: self.minimum_height
                    size_hint_y: None
                    cols: 1
                    spacing: '10dp'
                    BoxLabel:
                        text: _('Status')
                        value: root.status_str
                    BoxLabel:
                        text: _('Description') if root.description else ''
                        value: root.description
                    BoxLabel:
                        text: root.date_label
                        value: root.date_str
                    BoxLabel:
                        text: _('Amount sent') if root.is_mine else _('Amount received')
                        value: root.amount_str
                    BoxLabel:
                        text: _('Transaction fee') if root.fee_str else ''
                        value: root.fee_str
                    BoxLabel:
                        text: _('Transaction fee rate') if root.feerate_str else ''
                        value: root.feerate_str
                TopLabel:
                    text: _('Transaction ID') + ':' if root.tx_hash else ''
                TxHashLabel:
                    data: root.tx_hash
                    name: _('Transaction ID')
                TopLabel:
                    text: _('Outputs') + ':'
                OutputList:
                    id: output_list
        Widget:
            size_hint: 1, 0.1

        BoxLayout:
            size_hint: 1, None
            height: '48dp'
            Button:
                id: action_button
                size_hint: 0.5, None
                height: '48dp'
                text: ''
                disabled: True
                opacity: 0
                on_release: root.on_action_button_clicked()
            IconButton:
                size_hint: 0.5, None
                height: '48dp'
                icon: 'atlas://electrum/gui/kivy/theming/light/qrcode'
                on_release: root.show_qr()
            Button:
                size_hint: 0.5, None
                height: '48dp'
                text: _('Label')
                on_release: root.label_dialog()
            Button:
                size_hint: 0.5, None
                height: '48dp'
                text: _('Close')
                on_release: root.dismiss()
''')


class ActionButtonOption(NamedTuple):
    text: str
    func: Callable
    enabled: bool


class TxDialog(Factory.Popup):

    def __init__(self, app, tx):
        Factory.Popup.__init__(self)
        self.app = app  # type: ElectrumWindow
        self.wallet = self.app.wallet
        self.tx = tx  # type: Transaction
        self._action_button_fn = lambda btn: None

        # If the wallet can populate the inputs with more info, do it now.
        # As a result, e.g. we might learn an imported address tx is segwit,
        # or that a beyond-gap-limit address is is_mine.
        # note: this might fetch prev txs over the network.
        tx.add_info_from_wallet(self.wallet)

    def on_open(self):
        self.update()

    def update(self):
        format_amount = self.app.format_amount_and_units
        tx_details = self.wallet.get_tx_info(self.tx)
        tx_mined_status = tx_details.tx_mined_status
        exp_n = tx_details.mempool_depth_bytes
        amount, fee = tx_details.amount, tx_details.fee
        self.status_str = tx_details.status
        self.description = tx_details.label
        self.can_broadcast = tx_details.can_broadcast
        self.can_rbf = tx_details.can_bump
        self.can_dscancel = tx_details.can_dscancel
        self.tx_hash = tx_details.txid or ''
        if tx_mined_status.timestamp:
            self.date_label = _('Date')
            self.date_str = datetime.fromtimestamp(tx_mined_status.timestamp).isoformat(' ')[:-3]
        elif exp_n is not None:
            self.date_label = _('Mempool depth')
            self.date_str = _('{} from tip').format('%.2f MB'%(exp_n/1000000))
        else:
            self.date_label = ''
            self.date_str = ''

        self.can_sign = self.wallet.can_sign(self.tx)
        if amount is None:
            self.amount_str = _("Transaction unrelated to your wallet")
        elif amount > 0:
            self.is_mine = False
            self.amount_str = format_amount(amount)
        else:
            self.is_mine = True
            self.amount_str = format_amount(-amount)
        risk_of_burning_coins = (isinstance(self.tx, PartialTransaction)
                                 and self.can_sign
                                 and fee is not None
                                 and bool(self.wallet.get_warning_for_risk_of_burning_coins_as_fees(self.tx)))
        if fee is not None and not risk_of_burning_coins:
            self.fee_str = format_amount(fee)
            fee_per_kb = fee / self.tx.estimated_size() * 1000
            self.feerate_str = self.app.format_fee_rate(fee_per_kb)
        else:
            self.fee_str = _('unknown')
            self.feerate_str = _('unknown')
        self.ids.output_list.update(self.tx.outputs())

        for dict_entry in self.ids.output_list.data:
            dict_entry['color'], dict_entry['background_color'] = address_colors(self.wallet, dict_entry['address'])

        self.can_remove_tx = tx_details.can_remove
        self.update_action_button()

    def update_action_button(self):
        action_button = self.ids.action_button
        options = (
            ActionButtonOption(text=_('Sign'), func=lambda btn: self.do_sign(), enabled=self.can_sign),
            ActionButtonOption(text=_('Broadcast'), func=lambda btn: self.do_broadcast(), enabled=self.can_broadcast),
            ActionButtonOption(text=_('Bump fee'), func=lambda btn: self.do_rbf(), enabled=self.can_rbf),
            ActionButtonOption(text=_('Cancel (double-spend)'), func=lambda btn: self.do_dscancel(), enabled=self.can_dscancel),
            ActionButtonOption(text=_('Remove'), func=lambda btn: self.remove_local_tx(), enabled=self.can_remove_tx),
        )
        num_options = sum(map(lambda o: bool(o.enabled), options))
        # if no options available, hide button
        if num_options == 0:
            action_button.disabled = True
            action_button.opacity = 0
            return
        action_button.disabled = False
        action_button.opacity = 1

        if num_options == 1:
            # only one option, button will correspond to that
            for option in options:
                if option.enabled:
                    action_button.text = option.text
                    self._action_button_fn = option.func
        else:
            # multiple options. button opens dropdown which has one sub-button for each
            dropdown = DropDown()
            action_button.text = _('Options')
            self._action_button_fn = dropdown.open
            for option in options:
                if option.enabled:
                    btn = Button(text=option.text, size_hint_y=None, height='48dp')
                    btn.bind(on_release=option.func)
                    dropdown.add_widget(btn)

    def on_action_button_clicked(self):
        action_button = self.ids.action_button
        self._action_button_fn(action_button)

    def do_rbf(self):
        from .bump_fee_dialog import BumpFeeDialog
        fee = self.wallet.get_wallet_delta(self.tx).fee
        if fee is None:
            self.app.show_error(_("Can't bump fee: unknown fee for original transaction."))
            return
        size = self.tx.estimated_size()
        d = BumpFeeDialog(self.app, fee, size, self._do_rbf)
        d.open()

    def _do_rbf(self, new_fee_rate, is_final):
        if new_fee_rate is None:
            return
        try:
            new_tx = self.wallet.bump_fee(tx=self.tx,
                                          new_fee_rate=new_fee_rate)
        except CannotBumpFee as e:
            self.app.show_error(str(e))
            return
        if is_final:
            new_tx.set_rbf(False)
        self.tx = new_tx
        self.update()
        self.do_sign()

    def do_dscancel(self):
        from .dscancel_dialog import DSCancelDialog
        fee = self.wallet.get_wallet_delta(self.tx).fee
        if fee is None:
            self.app.show_error(_('Cannot cancel transaction') + ': ' + _('unknown fee for original transaction'))
            return
        size = self.tx.estimated_size()
        d = DSCancelDialog(self.app, fee, size, self._do_dscancel)
        d.open()

    def _do_dscancel(self, new_fee_rate):
        if new_fee_rate is None:
            return
        try:
            new_tx = self.wallet.dscancel(tx=self.tx,
                                          new_fee_rate=new_fee_rate)
        except CannotDoubleSpendTx as e:
            self.app.show_error(str(e))
            return
        self.tx = new_tx
        self.update()
        self.do_sign()

    def do_sign(self):
        self.app.protected(_("Sign this transaction?"), self._do_sign, ())

    def _do_sign(self, password):
        self.status_str = _('Signing') + '...'
        Clock.schedule_once(lambda dt: self.__do_sign(password), 0.1)

    def __do_sign(self, password):
        try:
            self.app.wallet.sign_transaction(self.tx, password)
        except InvalidPassword:
            self.app.show_error(_("Invalid PIN"))
        self.update()

    def do_broadcast(self):
        self.app.broadcast(self.tx)

    def show_qr(self):
        original_raw_tx = str(self.tx)
        qr_data = self.tx.to_qr_data()
        self.app.qr_dialog(_("Raw Transaction"), qr_data, text_for_clipboard=original_raw_tx)

    def remove_local_tx(self):
        txid = self.tx.txid()
        to_delete = {txid}
        to_delete |= self.wallet.get_depending_transactions(txid)
        question = _("Are you sure you want to remove this transaction?")
        if len(to_delete) > 1:
            question = (_("Are you sure you want to remove this transaction and {} child transactions?")
                        .format(len(to_delete) - 1))

        def on_prompt(b):
            if b:
                for tx in to_delete:
                    self.wallet.remove_transaction(tx)
                self.wallet.save_db()
                self.app._trigger_update_wallet()  # FIXME private...
                self.dismiss()
        d = Question(question, on_prompt)
        d.open()

    def label_dialog(self):
        from .label_dialog import LabelDialog
        key = self.tx.txid()
        text = self.app.wallet.get_label_for_txid(key)
        def callback(text):
            self.app.wallet.set_label(key, text)
            self.update()
            self.app.history_screen.update()
        d = LabelDialog(_('Enter Transaction Label'), text, callback)
        d.open()
