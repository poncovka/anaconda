# The base classes for Anaconda TUI Spokes
#
# Copyright (C) (2012)  Red Hat, Inc.
#
# This copyrighted material is made available to anyone wishing to use,
# modify, copy, or redistribute it subject to the terms and conditions of
# the GNU General Public License v.2, or (at your option) any later version.
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY expressed or implied, including the implied warranties of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General
# Public License for more details.  You should have received a copy of the
# GNU General Public License along with this program; if not, write to the
# Free Software Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301, USA.  Any Red Hat trademarks that are incorporated in the
# source code or documentation are not subject to the GNU General Public
# License and may only be used or replicated with the express permission of
# Red Hat, Inc.
#

import re
from collections import namedtuple

from pyanaconda.ui.common import Spoke, StandaloneSpoke, NormalSpoke
from pyanaconda.ui.tui.tuiobject import TUIObject
from pyanaconda.users import cryptPassword
from pyanaconda.iutil import setdeepattr, getdeepattr
from pyanaconda.i18n import N_, _
from pyanaconda import constants
from pyanaconda import ihelp
from pyanaconda import input_checking

from simpleline.render.adv_widgets import HelpScreen, YesNoDialog
from simpleline.render.containers import WindowContainer
from simpleline.render.screen import InputState
from simpleline.render.screen_handler import ScreenHandler
from simpleline.render.prompt import Prompt
from simpleline.render.widgets import Widget, CheckboxWidget, TextWidget, ColumnWidget

__all__ = ["TUISpoke", "EditTUISpoke", "EditTUIDialog", "EditTUISpokeEntry",
           "StandaloneSpoke", "NormalTUISpoke"]


# Inherit abstract methods from Spoke
# pylint: disable=abstract-method
class TUISpoke(TUIObject, Widget, Spoke):
    """Base TUI Spoke class implementing the pyanaconda.ui.common.Spoke API.
       It also acts as a Widget so we can easily add it to Hub, where is shows
       as a summary box with title, description and completed checkbox.

       :param category: category this spoke belongs to
       :type category: string

       .. inheritance-diagram:: TUISpoke
          :parts: 3
    """

    def __init__(self, data, storage, payload, instclass):
        if self.__class__ is TUISpoke:
            raise TypeError("TUISpoke is an abstract class")

        TUIObject.__init__(self, data)
        Widget.__init__(self)
        Spoke.__init__(self, storage, payload, instclass)

        self.input_required = True
        self.title = N_("Default spoke title")

    @property
    def status(self):
        return _("testing status...")

    @property
    def completed(self):
        return True

    def refresh(self, args=None):
        TUIObject.refresh(self, args)

    def input(self, args, key):
        """Handle the input, the base class just forwards it to the App level."""
        return key

    def render(self, width):
        """Render the summary representation for Hub to internal buffer."""
        Widget.render(self, width)

        if self.mandatory and not self.completed:
            key = "!"
        elif self.completed:
            key = "x"
        else:
            key = " "

        # always set completed = True here; otherwise key value won't be
        # displayed if completed (spoke value from above) is False
        c = CheckboxWidget(key=key, completed=True,
                           title=_(self.title), text=self.status)
        c.render(width)
        self.draw(c)


class NormalTUISpoke(TUISpoke, NormalSpoke):
    """
       .. inheritance-diagram:: NormalTUISpoke
          :parts: 3
    """

    def input(self, args, key):
        """Handle the input."""
        # TRANSLATORS: 'h' to help
        if key.lower() == Prompt.HELP:
            if self.has_help:
                help_path = ihelp.get_help_path(self.helpFile, self.instclass, True)
                ScreenHandler.push_screen_modal(HelpScreen(help_path))
                self.redraw()
                return InputState.PROCESSED

        return super(NormalTUISpoke, self).input(args, key)

    def prompt(self, args=None):
        """Return the prompt."""
        prompt = TUISpoke.prompt(self, args)

        if self.has_help:
            prompt.add_help_option()

        return prompt

EditTUISpokeEntry = namedtuple("EditTUISpokeEntry", ["title", "attribute", "aux", "visible"])


# Inherit abstract methods from NormalTUISpoke
# pylint: disable=abstract-method
class EditTUIDialog(NormalTUISpoke):
    """Spoke/dialog used to read new value of textual or password data

       .. inheritance-diagram:: EditTUIDialog
          :parts: 3

       To override the wrong input message set the wrong_input_message attribute
       to a translated string.
    """
    PASSWORD = re.compile(".*")

    def __init__(self, data, storage, payload, instclass, policy_name=""):
        if self.__class__ is EditTUIDialog:
            raise TypeError("EditTUIDialog is an abstract class")

        NormalTUISpoke.__init__(self, data, storage, payload, instclass)
        self.title = N_("New value")
        self.input_required = True
        self.value = None
        self.policy = None
        self.wrong_input_message = None

        # Configure the password policy, if available. Otherwise use defaults.
        self.policy = self.data.anaconda.pwpolicy.get_policy(policy_name)
        if not self.policy:
            self.policy = self.data.anaconda.PwPolicyData()

    def refresh(self, args=None):
        self._window = WindowContainer()
        self.value = None

    def prompt(self, args=None):
        entry = args
        if not entry:
            return None

        if entry.aux == self.PASSWORD:
            pw = self.get_user_input(_("%s: ") % entry.title, hidden=True)
            confirm = self.get_user_input(_("%s (confirm): ") % entry.title, hidden=True)

            if (pw and not confirm) or (confirm and not pw):
                print(_("You must enter your root password and confirm it by typing"
                        " it a second time to continue."))
                return None
            if pw != confirm:
                print(_(constants.PASSWORD_CONFIRM_ERROR_TUI) % {"password_name_plural": _(constants.NAME_OF_PASSWORD_PLURAL)})
                return None

            # If an empty password was provided, unset the value
            if not pw:
                self.value = ""
                return None

            # prepare a password validation request
            check_request = input_checking.PasswordCheckRequest()
            check_request.password=pw
            check_request.password_confirmation=""
            check_request.policy=self.policy

            # validate the password
            check = input_checking.PasswordValidityCheck()
            check.run(check_request)

            # if the score is equal to 0 and we have an error message set
            if not check.result.password_score and check.result.error_message:
                print(check.result.error_message)
                return None

            if check.result.password_quality < self.policy.minquality:
                if self.policy.strict:
                    done_msg = ""
                else:
                    done_msg = _("\nWould you like to use it anyway?")

                if check.result.error_message:
                    main_message = _(constants.PASSWORD_WEAK_WITH_ERROR) % {"password_name": _(constants.NAME_OF_PASSWORD),
                                                                            "error_message": check.result.error_message}
                    error = main_message + " " + done_msg
                else:
                    error = _(constants.PASSWORD_WEAK) % {"password_name": _(constants.NAME_OF_PASSWORD)} + " " + done_msg

                if not self.policy.strict:
                    question_window = YesNoDialog(error)
                    ScreenHandler.push_screen_modal(question_window)
                    if not question_window.answer:
                        return None
                else:
                    print(error)
                    return None

            if any(char not in constants.PW_ASCII_CHARS for char in pw):
                print(_("You have provided a password containing non-ASCII characters.\n"
                        "You may not be able to switch between keyboard layouts to login.\n"))

            self.value = cryptPassword(pw)
            return None
        else:
            return Prompt(_("Enter a new value for '%(title)s' and press %(enter)s") % {
                # TRANSLATORS: 'title' as a title of the entry
                "title": entry.title,
                # TRANSLATORS: 'enter' as the key ENTER
                "enter": Prompt.ENTER
            })

    def input(self, args, key):
        entry = args

        if callable(entry.aux):
            valid, err_msg = entry.aux(key)
            if not valid:
                if err_msg is not None:
                    self.wrong_input_message = err_msg
        else:
            valid = entry.aux.match(key)

        if valid:
            self.value = key
            self.close()
            return InputState.PROCESSED
        else:
            if self.wrong_input_message:
                print(self.wrong_input_message)
            else:
                print(_("You have provided an invalid value\n"))
            return NormalTUISpoke.input(self, entry, key)


class OneShotEditTUIDialog(EditTUIDialog):
    """The same as EditTUIDialog, but closes automatically after
       the value is read
    """

    def prompt(self, args=None):
        entry = args
        ret = None
        self.value = None

        if entry:
            while self.value is None and ret is None:
                ret = EditTUIDialog.prompt(self, entry)

            if ret is None:
                self.close()

        return ret


# Inherit abstract methods from NormalTUISpoke
# pylint: disable=abstract-method
class EditTUISpoke(NormalTUISpoke):
    """Spoke with declarative semantics, it contains
       a list of titles, attribute names and regexps
       that specify the fields of an object the user
       allowed to edit.

       .. inheritance-diagram:: EditTUISpoke
          :parts: 3
    """

    # self.data's subattribute name
    # empty string means __init__ will provide
    # something else
    edit_data = ""

    # constants to be used in the aux field
    # and mark the entry as a password or checkbox field
    PASSWORD = EditTUIDialog.PASSWORD
    CHECK = "check"

    # list of fields in the format of named tuples like:
    # EditTUISpokeEntry(title, attribute, aux, visible)
    # title     - Nontranslated title of the entry
    # attribute - The edited object's attribute name
    # aux       - Compiled regular expression or
    #             a callable taking the value and
    #             returning (valid:bool, err_msg:str) tuple,
    #             or one of the two constants from above.
    #             It will be used to check the value typed
    #             by user and to show the proper entry
    #             for password, text or checkbox.
    # visible   - True, False or a function that accepts
    #             two arguments - self and the edited object
    #             It is evaluated and used to display or
    #             hide this attribute's entry
    edit_fields = [
    ]

    def __init__(self, data, storage, payload, instclass, policy_name=""):
        if self.__class__ is EditTUISpoke:
            raise TypeError("EditTUISpoke is an abstract class")

        NormalTUISpoke.__init__(self, data, storage, payload, instclass)

        self.dialog = OneShotEditTUIDialog(data, storage, payload, instclass, policy_name=policy_name)

        # self.args should hold the object this Spoke is supposed
        # to edit
        self.args = None

    @property
    def visible_fields(self):
        """Get the list of currently visible entries"""

        # it would be nice to have this a static list, but visibility of the
        # entries often depends on the current state of the spoke and thus
        # changes dynamically
        ret = []
        for entry in self.edit_fields:
            if callable(entry.visible) and entry.visible(self, self.args):
                ret.append(entry)
            elif not callable(entry.visible) and entry.visible:
                ret.append(entry)

        return ret

    def refresh(self, args=None):
        NormalTUISpoke.refresh(self, args)

        if args:
            self.args = args
        elif self.edit_data:
            self.args = self.data
            for key in self.edit_data.split("."):
                self.args = getattr(self.args, key)

        def _prep_text(i, entry):
            number = TextWidget("%2d)" % i)
            title = TextWidget(_(entry.title))
            value = getdeepattr(self.args, entry.attribute)
            value = TextWidget(value)

            return ColumnWidget([(3, [number]), (None, [title, value])], 1)

        def _prep_check(i, entry):
            number = TextWidget("%2d)" % i)
            value = getdeepattr(self.args, entry.attribute)
            ch = CheckboxWidget(title=_(entry.title), completed=bool(value))

            return ColumnWidget([(3, [number]), (None, [ch])], 1)

        def _prep_password(i, entry):
            number = TextWidget("%2d)" % i)
            title = TextWidget(_(entry.title))
            value = ""
            if len(getdeepattr(self.args, entry.attribute)) > 0:
                value = _("Password set.")
            value = TextWidget(value)

            return ColumnWidget([(3, [number]), (None, [title, value])], 1)

        for idx, entry in enumerate(self.visible_fields):
            entry_type = entry.aux
            if entry_type == self.PASSWORD:
                w = _prep_password(idx+1, entry)
            elif entry_type == self.CHECK:
                w = _prep_check(idx+1, entry)
            else:
                w = _prep_text(idx+1, entry)

            self.window.add(w)

        if self.visible_fields:
            self.window.add_separator()

    def input(self, args, key):
        try:
            idx = int(key) - 1
            if idx >= 0 and idx < len(self.visible_fields):
                if self.visible_fields[idx].aux == self.CHECK:
                    setdeepattr(self.args, self.visible_fields[idx].attribute,
                                not getdeepattr(self.args, self.visible_fields[idx][1]))
                    self.redraw()
                    self.apply()
                else:
                    ScreenHandler.push_screen_modal(self.dialog, self.visible_fields[idx])
                    self.redraw()
                    if self.dialog.value is not None:
                        setdeepattr(self.args, self.visible_fields[idx].attribute,
                                    self.dialog.value)
                        self.apply()
                return InputState.PROCESSED
        except ValueError:
            pass

        return NormalTUISpoke.input(self, args, key)


class StandaloneTUISpoke(TUISpoke, StandaloneSpoke):
    """
       .. inheritance-diagram:: StandaloneTUISpoke
          :parts: 3
    """
    pass
