#!/usr/bin/env python3

r"""jami_commander.py.

For help and documentation, please read the README.md file.
Online available at:
https://github.com/8go/jami-commander/blob/master/README.md

DBUS API can be found here:
https://git.jami.net/savoirfairelinux/jami-daemon/-/blob/master/bin/dbus/cx.ring.Ring.ConfigurationManager.xml?ref_type=heads

"""

# 234567890123456789012345678901234567890123456789012345678901234567890123456789
# 000000001111111111222222222233333333334444444444555555555566666666667777777777

# automatically sorted by isort,
# then formatted by black --line-length 79


import argparse
import asyncio
import errno
import json
import logging
import os
import os.path
import re  # regular expression
import select
import subprocess
import sys
import tempfile
import textwrap
import time
import traceback
import urllib.request
import uuid
from importlib import metadata
from os import R_OK, access
from os.path import isfile
from typing import Literal, Union

import emoji
import markdown

# local
from .controller import libjamiCtrl

# version number
VERSION = "2024-08-25"
VERSIONNR = "0.8.0"
# jami-commander; for backwards compitability replace _ with -
PROG_WITHOUT_EXT = os.path.splitext(os.path.basename(__file__))[0].replace(
    "_", "-"
)
# jami-commander.py; for backwards compitability replace _ with -
PROG_WITH_EXT = os.path.basename(__file__).replace("_", "-")


# usually there are no permissions for using: /run/jami-commander.pid
# so instead local files like ~/.run/jami-commander.some-uuid-here.pid will
# be used for storing the PID(s) for sending signals.
# There might be more than 1 process running in parallel, so there might be
# more than 1 PID at a given point in time.
PID_DIR_DEFAULT = os.path.normpath(os.path.expanduser("~/.run/"))
PID_FILE_DEFAULT = os.path.normpath(
    PID_DIR_DEFAULT + "/" + PROG_WITHOUT_EXT + "." + str(uuid.uuid4()) + ".pid"
)

PRINT = "print"  # version type
CHECK = "check"  # version type


OUTPUT_TEXT = "text"
# json, as close to data that is provided, a few convenient fields added
# transport_response removed
OUTPUT_JSON = "json"
OUTPUT_DEFAULT = OUTPUT_TEXT

# location of README.md file if it is not found on local harddisk
# used for --manual
README_FILE_RAW_URL = (
    "https://raw.githubusercontent.com/8go/jami-commander/master/README.md"
)

DEFAULT_SEPARATOR = "    "  # used for sperating columns in print outputs
SEP = DEFAULT_SEPARATOR

VERSION_UNUSED_DEFAULT = None  # use None if --version is not specified
VERSION_USED_DEFAULT = PRINT  # use 'print' by default with --version

ACCT_TYPE_RING = "RING"
DEFAUL_ACCT_TYPE = ACCT_TYPE_RING

# increment this number and use new incremented number for next warning
# last unique Wxxx warning number used: W113:
# increment this number and use new incremented number for next error
# last unique Exxx error number used: E255:


class LooseVersion:
    """Version numbering and comparison.
    See https://github.com/effigies/looseversion/blob/main/looseversion.py.
    Argument 'other' must be of type LooseVersion.
    """

    component_re = re.compile(r"(\d+ | [a-z]+ | \.)", re.VERBOSE)

    def __init__(self, vstring=None):
        if vstring:
            self.parse(vstring)

    def __eq__(self, other):
        return self._cmp(other) == 0

    def __lt__(self, other):
        return self._cmp(other) < 0

    def __le__(self, other):
        return self._cmp(other) <= 0

    def __gt__(self, other):
        return self._cmp(other) > 0

    def __ge__(self, other):
        return self._cmp(other) >= 0

    def parse(self, vstring):
        self.vstring = vstring
        components = [
            x for x in self.component_re.split(vstring) if x and x != "."
        ]
        for i, obj in enumerate(components):
            try:
                components[i] = int(obj)
            except ValueError:
                pass
        self.version = components

    def __str__(self):
        return self.vstring

    def __repr__(self):
        return "LooseVersion ('%s')" % str(self)

    def _cmp(self, other):
        if self.version == other.version:
            return 0
        if self.version < other.version:
            return -1
        if self.version > other.version:
            return 1


class JamiCommanderError(Exception):
    pass


class JamiCommanderWarning(Warning):
    pass


class GlobalState:
    """Keep global variables.

    Trivial class to help keep some global state.
    """

    def __init__(self):
        """Store global state."""
        self.log: logging.Logger = None  # logger object
        self.pa: argparse.Namespace = None  # parsed arguments
        # to which logic (message, file) is
        # stdin pipe assigned?
        self.stdin_use: str = "none"
        self.ctrl: libjamiCtrl = None
        self.account: Union[None, str] = None
        self.send_action = False  # argv contains send action
        self.listen_action = False  # argv contains listen action
        self.accountmgmt_action = False  # argv contains account action
        self.conversation_action = False  # argv contains conversation action
        self.set_action = False  # argv contains set action
        self.get_action = False  # argv contains get action
        self.setget_action = False  # argv contains set or get action
        self.err_count = 0  # how many errors have occurred so far
        self.warn_count = 0  # how many warnings have occurred so far


# Convert None to "", useful when reporting values to stdout
# Should only be called with a) None or b) a string.
# We want to avoid situation where we would print: name = None
def zn(str):
    return str or ""


def get_qualifiedclassname(obj):
    klass = obj.__class__
    module = klass.__module__
    if module == "builtins":
        return klass.__qualname__  # avoid outputs like 'builtins.str'
    return module + "." + klass.__qualname__


def print_output(
    option: Literal["text", "json"],
    *,
    text: str,
    json_: dict = None,
) -> None:
    """Print output according to which option is specified with --output"""
    # json_ has the underscore to avoid a name clash with the module json
    results = {
        OUTPUT_TEXT: text,
        OUTPUT_JSON: json_,
    }
    if option == OUTPUT_TEXT:
        print(results[option], flush=True)
    else:
        # print(json.dumps(results[option]), flush=True)
        print(json.dumps(results[option], default=obj_to_dict), flush=True)


def obj_to_dict(obj):
    """Return dict of object

    Useful for json.dump() dict-to-json conversion.
    """
    if gs.pa.verbose > 1:  # 2+
        gs.log.debug(f"obj_to_dict: {obj.__class__}")
        gs.log.debug(f"obj_to_dict: {obj.__class__.__name__}")
        gs.log.debug(f"obj_to_dict: {get_qualifiedclassname(obj)}")
    # this one is crucial, it make the serialization circular reference.
    if get_qualifiedclassname(obj) == "aiohttp.streams.StreamReader":
        return {obj.__class__.__name__: str(obj)}
    # these four are crucial, they make the serialization circular reference.
    if (
        get_qualifiedclassname(obj)
        == "asyncio.unix_events._UnixSelectorEventLoop"
    ):
        return {obj.__class__.__name__: str(obj)}
    if get_qualifiedclassname(obj) == "aiohttp.tracing.Trace":
        return {obj.__class__.__name__: str(obj)}
    if get_qualifiedclassname(obj) == "aiohttp.tracing.TraceConfig":
        return {obj.__class__.__name__: str(obj)}
    # avoid "keys must be str, int, float, bool or None" errors
    if get_qualifiedclassname(obj) == "aiohttp.connector.TCPConnector":
        return {obj.__class__.__name__: str(obj)}

    if hasattr(obj, "__dict__"):
        if gs.pa.verbose > 1:  # 2+
            gs.log.debug(
                f"{obj} is not serializable, using its available dictionary "
                f"{obj.__dict__}."
            )
        return obj.__dict__
    else:
        # gs.log.debug(
        #     f"Object {obj} ({type(obj)}) has no class dictionary. "
        #     "Cannot be converted to JSON object. "
        #     "Will be converted to JSON string."
        # )
        # simple types like yarl.URL do not have a __dict__
        # get the class name as string, create a dict with classname and value
        if gs.pa.verbose > 1:  # 2+
            gs.log.debug(
                f"{obj} is not serializable, simplifying to key value pair "
                f"key '{obj.__class__.__name__}' and value '{str(obj)}'."
            )
        return {obj.__class__.__name__: str(obj)}


def create_pid_file() -> None:
    """Write PID to disk.

    If possible create a PID file. This is not essential.
    So, if it fails there is no problem. The PID file can
    be helpful to send a kill signal or similar to the process.
    E.g. to stop listening.
    Because the user can start several processes at the same time,
    just having one PID file is not acceptable because a newly started
    process would overwrite the previous PID file. We use UUIDs to make
    each PID file unique.
    """
    try:
        if not os.path.exists(PID_DIR_DEFAULT):
            os.mkdir(PID_DIR_DEFAULT)
            gs.log.debug(f"Create directory {PID_DIR_DEFAULT} for PID file.")
        pid = os.getpid()
        gs.log.debug(f"Trying to create a PID file to store process id {pid}.")
        with open(PID_FILE_DEFAULT, "w") as f:  # overwrite
            f.write(str(pid))
            f.close()
        gs.log.debug(
            f'Successfully created PID file "{PID_FILE_DEFAULT}" '
            f"to store process id {pid}."
        )
    except Exception:
        gs.log.debug(
            f'Failed to create PID file "{PID_FILE_DEFAULT}" '
            f"to store process id {os.getpid()}."
        )


def delete_pid_file() -> None:
    """Remove PID file from disk.

    Clean up by removing PID file.
    It might not exist. So, ignore failures.
    """
    try:
        os.remove(PID_FILE_DEFAULT)
    except Exception:
        gs.log.debug(f'Failed to remove PID file "{PID_FILE_DEFAULT}".')


def cleanup() -> None:
    """Cleanup before quiting program."""
    gs.log.debug("Cleanup: cleaning up.")
    delete_pid_file()


def action_add_account() -> None:
    """Add account."""
    # gs.pa.add_account : ALIAS HOSTNAME USERNAME PASSWORD
    accountdetails = {
        "Account.type": DEFAUL_ACCT_TYPE,
        "Account.alias": gs.pa.add_account[0],
        "Account.hostname": gs.pa.add_account[1],
        "Account.username": gs.pa.add_account[2],
        "Account.password": gs.pa.add_account[3],
    }
    gs.log.debug(f"Adding account with these details: {accountdetails}")
    accountid = gs.ctrl.addAccount(accountdetails)
    json_ = {"accountid": accountid}
    text = accountid
    # output format controlled via --output flag
    # json_.pop("transport_response")
    print_output(
        gs.pa.output,
        text=text,
        json_=json_,
    )


def action_remove_account() -> None:
    """Remove account."""
    for acct in gs.pa.remove_account:
        gs.log.debug(f'Submitted account "{acct}" for removal.')
        gs.ctrl.removeAccount(acct)


def action_get_enabled_accounts() -> None:
    """Get enabled account ids."""
    accts = gs.ctrl.getAllEnabledAccounts()
    json_ = {"accountids": accts}
    text = ""
    for acct in accts:
        text += f"{acct}\n"
    text = text.strip()
    # output format controlled via --output flag
    # json_.pop("transport_response")
    print_output(
        gs.pa.output,
        text=text,
        json_=json_,
    )


def action_get_conversations() -> None:
    """Get swarm conversation ids associated with the account."""
    convs = gs.ctrl.getConversations(gs.account)
    json_ = {"accountid": gs.account, "conversationids": convs}
    text = ""
    for conv in convs:
        text += f"{conv}\n"
    text = text.strip()
    # output format controlled via --output flag
    # json_.pop("transport_response")
    print_output(
        gs.pa.output,
        text=text,
        json_=json_,
    )


def action_add_conversation() -> None:
    """Add swarm conversation to the account."""
    convid = gs.ctrl.startConversation(gs.account)
    json_ = {"accountid": gs.account, "conversationid": convid}
    text = convid
    # output format controlled via --output flag
    # json_.pop("transport_response")
    print_output(
        gs.pa.output,
        text=text,
        json_=json_,
    )


def action_remove_conversation() -> None:
    """Remove swarm conversation to the account."""
    text = ""
    rmlist = []
    for conv in gs.pa.conversations:
        resp = gs.ctrl.removeConversation(gs.account, conv)
        rmlist.append({"conversationid": conv, "success": resp})
        text += f"{gs.account}{SEP}{conv}{SEP}success={resp}\n"
        if resp == 1:
            gs.log.debug(
                f"Conversation {conv} was successfully removed "
                f"from account {gs.account}."
            )
        else:
            gs.log.error(
                f"Conversation {conv} could not be removed "
                f"from account {gs.account}. We skip this."
            )
            gs.err_count += 1
    text = text.strip()
    json_ = {"accountid": gs.account, "remove": rmlist}
    # output format controlled via --output flag
    # json_.pop("transport_response")
    print_output(
        gs.pa.output,
        text=text,
        json_=json_,
    )


def action_get_conversation_members() -> None:
    """Get members from swarm conversations associated with the account."""
    if gs.pa.conversations is None:
        gs.log.info(
            "No conversations specified. "
            "Add --conversations in order to use --get-conversation-members."
        )
        return
    memberslist = []
    text = ""
    for conv in gs.pa.conversations:
        members = gs.ctrl.getConversationMembers(gs.account, conv)
        gs.log.debug(f"members: {members} {type(members)}")
        # members is an array of dictionaries
        # dictionaries have members: lastDisplayed, role, uri
        # the 'uri' is the userid
        # the role could be 'member' or 'admin' or 'invited' or 'banned'
        memberslist.append(
            {
                "accountid": gs.account,
                "conversationid": conv,
                "contacturis": members,
            }
        )
        text += (
            f"accountid {gs.account}{SEP}conversationid {conv}{SEP}userids "
        )
        for member in members:
            text += f"{member["uri"]}{SEP}"
        text += "\n"
    json_ = {"accountid": gs.account, "members": memberslist}
    text = text.strip()
    # output format controlled via --output flag
    # json_.pop("transport_response")
    print_output(
        gs.pa.output,
        text=text,
        json_=json_,
    )


def action_add_conversation_member() -> None:
    """This will invite a user to a conversation."""
    if gs.pa.conversations is None:
        gs.log.info(
            "No conversations specified. "
            "Add --conversations in order to use --get-conversation-members."
        )
        return
    for conv in gs.pa.conversations:
        for userid in gs.pa.add_conversation_member:
            gs.log.debug(
                f"Submitted user {userid} to be added to "
                f"conversation {conv} in account {gs.account} as members."
            )
            gs.ctrl.addConversationMember(gs.account, conv, userid)


def action_remove_conversation_member() -> None:
    """This will ban a user from a conversation."""
    if gs.pa.conversations is None:
        gs.log.info(
            "No conversations specified. "
            "Add --conversations in order to use --get-conversation-members."
        )
        return
    for conv in gs.pa.conversations:
        for userid in gs.pa.remove_conversation_member:
            gs.log.debug(
                f"Submitted user {userid} to be removed from "
                f"conversation {conv} in account {gs.account} as members."
            )
            gs.ctrl.removeConversationMember(gs.account, conv, userid)


# according to linter: function is too complex, C901
async def send_file(conversations, file):  # noqa: C901
    """Process file.

    Send file to conversation.

    Arguments:
    ---------
    conversations : list
        list of conversationid-s
    file : str
        file name of file from --file argument

    """
    if not conversations:
        gs.log.info(
            "No conversations are given. This should not happen. "
            "This file is being dropped and NOT sent."
        )
        return

    if file == "-":  # - means read as pipe from stdin
        isPipe = True
        fin_buf = sys.stdin.buffer.read()
        len_fin_buf = len(fin_buf)
        file = "mc-" + str(uuid.uuid4()) + ".tmp"
        gs.log.debug(
            f"{len_fin_buf} bytes of file data read from stdin. "
            f'Temporary file "{file}" was created for file.'
        )
        fout = open(file, "wb")
        fout.write(fin_buf)
        fout.close()
    else:
        isPipe = False

    if not os.path.isfile(file):
        gs.log.debug(
            f"File {file} is not a file. Doesn't exist or "
            "is a directory. "
            "This file is being dropped and NOT sent."
        )
        return

    try:
        for conversation in conversations:
            resp = gs.ctrl.sendFile(
                gs.account,
                conversation,
                os.path.abspath(file),
                fileDisplayName=os.path.basename(file),
                replyTo="",
            )
            # this never returns anything, resp == None
            gs.log.debug(f"ctrl.sendFile() returned {resp}.")
            gs.log.info(
                f'An attempt was made to send file "{file}" '
                f'to conversation "{conversation}". Response was {resp}.'
            )
    except Exception:
        gs.log.error("E147: " f"File send of file {file} failed. Sorry.")
        gs.err_count += 1
        gs.log.debug("Here is the traceback.\n" + traceback.format_exc())

    if isPipe:
        # rm temp file
        os.remove(file)


# according to linter: function is too complex, C901
async def send_message(conversations, message):  # noqa: C901
    """Process message.

    Format message according to instructions from command line arguments.
    Then send the one message to all conversations.

    Arguments:
    ---------
    conversations : list
        list of conversationsid-s
    message : str
        message to send as read from -m, pipe or keyboard
        message is without mime formatting

    """
    if not conversations:
        gs.log.info(
            "No conversations are given. This should not happen. "
            "This text message is being dropped and NOT sent."
        )
        return
    # remove leading AND trailing newlines to beautify
    message = message.strip("\n")

    if message.strip() == "":
        gs.log.debug(
            "The message is empty. "
            "This message is being dropped and NOT sent."
        )
        return

    if gs.pa.code:
        gs.log.debug('Sending message in format "code".')
        formatted_message = "<pre><code>" + message + "\n</code></pre>\n"
        # next line: work-around for Element Android
        message = "```\n" + message + "\n```"  # to format it as code
        formatted_message = message
    elif gs.pa.markdown:
        gs.log.debug(
            "Converting message from MarkDown into HTML. "
            'Sending message in format "markdown".'
        )
        # e.g. converts from "-abc" to "<ul><li>abc</li></ul>"
        formatted_message = markdown(message)
    elif gs.pa.html:
        gs.log.debug('Sending message in format "html".')
        formatted_message = message  # the same for the time being
    elif gs.pa.emojize:
        gs.log.debug('Sending message in format "emojized".')
        # convert emoji shortcodes if present
        formatted_message = emoji.emojize(message)
    else:
        gs.log.debug('Sending message in format "text".')
        formatted_message = message

    try:
        for conversation in conversations:
            resp = gs.ctrl.sendMessage(
                gs.account,
                conversation,
                formatted_message,
                commitId="",
                flag=0,
            )
            # this never returns anything, resp == None
            gs.log.debug(f"ctrl.sendMessage() returned {resp}.")
            gs.log.info(
                f'An attempt was made to send message "{message}" '
                f'to conversation "{conversation}". Response was {resp}.'
            )
    except Exception:
        gs.log.error("E151: " "Message send failed. Sorry.")
        gs.err_count += 1
        gs.log.debug("Here is the traceback.\n" + traceback.format_exc())


async def stream_messages_from_pipe(conversations):
    """Read input from pipe if available.

    Read pipe line by line. For each line received, immediately
    send it.

    Arguments:
    ---------
    conversations : list of conversationids

    """
    stdin_ready = select.select(
        [
            sys.stdin,
        ],
        [],
        [],
        0.0,
    )[  # noqa
        0
    ]  # noqa
    if not stdin_ready:
        gs.log.debug(
            "stdin is not ready for streaming. "
            "A pipe could be used, but pipe could be empty, "
            "stdin could also be a keyboard."
        )
    else:
        gs.log.debug(
            "stdin is ready. Something "
            "is definitely piped into program from stdin. "
            "Reading message from stdin pipe."
        )
    if ((not stdin_ready) and (not sys.stdin.isatty())) or stdin_ready:
        if not sys.stdin.isatty():
            gs.log.debug(
                "Pipe was definitely used, but pipe might be empty. "
                "Trying to read from pipe in any case."
            )
        try:
            for line in sys.stdin:
                await send_message(conversations, line)
                gs.log.debug("Using data from stdin pipe stream as message.")
        except EOFError:  # EOF when reading a line
            gs.log.debug(
                "Reading from stdin resulted in EOF. This can happen "
                "when a pipe was used, but the pipe is empty. "
                "No message will be generated."
            )
        except UnicodeDecodeError:
            gs.log.info(
                "Reading from stdin resulted in UnicodeDecodeError. This "
                "can happen if you try to pipe binary data for a text "
                "message. For a text message only pipe text via stdin, "
                "not binary data. No message will be generated."
            )


def get_messages_from_pipe() -> list:
    """Read input from pipe if available.

    Return [] if no input available on pipe stdin.
    Return ["some-msg"] if input is availble.
    Might also return [""] of course if "" was in pipe.
    Currently there is at most 1 msg in the returned list.
    """
    messages = []
    stdin_ready = select.select(
        [
            sys.stdin,
        ],
        [],
        [],
        0.0,
    )[  # noqa
        0
    ]  # noqa
    if not stdin_ready:
        gs.log.debug(
            "stdin is not ready for reading. "
            "A pipe could be used, but pipe could be empty, "
            "stdin could also be a keyboard."
        )
    else:
        gs.log.debug(
            "stdin is ready. Something "
            "is definitely piped into program from stdin. "
            "Reading message from stdin pipe."
        )
    if ((not stdin_ready) and (not sys.stdin.isatty())) or stdin_ready:
        if not sys.stdin.isatty():
            gs.log.debug(
                "Pipe was definitely used, but pipe might be empty. "
                "Trying to read from pipe in any case."
            )
        message = ""
        try:
            for line in sys.stdin:
                message += line
            gs.log.debug("Using data from stdin pipe as message.")
            messages.append(message)
        except EOFError:  # EOF when reading a line
            gs.log.debug(
                "Reading from stdin resulted in EOF. This can happen "
                "when a pipe was used, but the pipe is empty. "
                "No message will be generated."
            )
        except UnicodeDecodeError:
            gs.log.info(
                "Reading from stdin resulted in UnicodeDecodeError. This "
                "can happen if you try to pipe binary data for a text "
                "message. For a text message only pipe text via stdin, "
                "not binary data. No message will be generated."
            )
    return messages


def get_messages_from_keyboard() -> list:
    """Read input from keyboard but only if no other messages are available.

    If there is a message provided via --message argument, no message
    will be read from keyboard.
    If there are other send operations like --image, --file, etc. are
    used, no message will be read from keyboard.
    If there is a message provided via stdin input pipe, no message
    will be read from keyboard.
    In short, we only read from keyboard as last resort, if no messages are
    specified or provided anywhere and no other send-operations like
    --image, --event, etc. are performed.

    Return [] if no input available on keyboard.
    Return ["some-msg"] if input is availble on keyboard.
    Might also return [""] of course if "" keyboard entry was empty.
    Currently there is at most 1 msg in the returned list.
    """
    messages = []
    if gs.pa.message:
        gs.log.debug(
            "Don't read from keyboard because there are "
            "messages provided in arguments with -m."
        )
        return messages  # return empty list because mesgs in -m
    if gs.pa.file or gs.pa.version:
        gs.log.debug(
            "Don't read from keyboard because there are "
            "other send operations or --version provided in arguments."
        )
        return messages  # return empty list because mesgs in -m
    stdin_ready = select.select(
        [
            sys.stdin,
        ],
        [],
        [],
        0.0,
    )[  # noqa
        0
    ]  # noqa
    if not stdin_ready:
        gs.log.debug(
            "stdin is not ready for keyboard interaction. "
            "A pipe could be used, but pipe could be empty, "
            "stdin could also be a keyboard."
        )
    else:
        gs.log.debug(
            "stdin is ready. Something "
            "is definitely piped into program from stdin. "
            "Reading message from stdin pipe."
        )
    if (not stdin_ready) and (sys.stdin.isatty()):
        # because sys.stdin.isatty() is true
        gs.log.debug(
            "No pipe was used, so read input from keyboard. "
            "Reading message from keyboard"
        )
        try:
            message = input("Enter message to send: ")
            gs.log.debug("Using data from stdin keyboard as message.")
            messages.append(message)
        except EOFError:  # EOF when reading a line
            gs.log.debug(
                "Reading from stdin resulted in EOF. "
                "Reading from keyboard failed. "
                "No message will be generated."
            )
    return messages


async def send_messages_and_files(conversations, messages):
    """Send text messages and files.

    First images, audio, etc, then text messaged.

    Arguments:
    ---------
    conversations : list of conversationsids
    messages : list of messages to send

    """
    if gs.pa.file:
        for file in gs.pa.file:
            await send_file(conversations, file)

    for message in messages:
        await send_message(conversations, message)


async def process_arguments_and_input(conversations):
    """Process arguments and all input.

    Process all input: text messages, etc.
    Prepare a list of messages from all sources and then send them.
    Before send all files.

    Arguments:
    ---------
    conversations : list of conversationids (destinations)

    """
    streaming = False
    messages_from_pipe = []
    if gs.stdin_use == "none":  # STDIN is unused
        messages_from_pipe = get_messages_from_pipe()
    messages_from_keyboard = get_messages_from_keyboard()
    if not gs.pa.message:
        messages_from_commandline = []
    else:
        messages_from_commandline = []
        for m in gs.pa.message:
            if m == "\\-":  # escaped -
                messages_from_commandline += ["-"]
            elif m == "\\_":  # escaped _
                messages_from_commandline += ["_"]
            elif m == "-":
                # stdin pipe, read and process everything in pipe as 1 msg
                messages_from_commandline += get_messages_from_pipe()
            elif m == "_":
                # streaming via pipe on stdin
                # stdin pipe, read and process everything in pipe line by line
                streaming = True
            else:
                messages_from_commandline += [m]

    gs.log.debug(f"Messages from pipe:         {messages_from_pipe}")
    gs.log.debug(f"Messages from keyboard:     {messages_from_keyboard}")
    gs.log.debug(f"Messages from command-line: {messages_from_commandline}")

    messages_all = (
        messages_from_commandline + messages_from_pipe + messages_from_keyboard
    )  # keyboard at end

    # loop thru all msgs and split them
    if gs.pa.split:
        # gs.pa.split can have escape characters, it has to be de-escaped
        decoded_string = bytes(gs.pa.split, "utf-8").decode("unicode_escape")
        gs.log.debug(f'String used for splitting is: "{decoded_string}"')
        messages_all_split = []
        for m in messages_all:
            messages_all_split += m.split(decoded_string)
    else:  # not gs.pa.split
        messages_all_split = messages_all

    if (gs.pa.file or messages_all_split) and not conversations:
        gs.log.error(
            "E255: "
            "No conversations are given. Specify --conversations. "
            "Nothing is being sent. Try again with --conversations set."
        )
        gs.err_count += 1
        return

    await send_messages_and_files(conversations, messages_all_split)
    # now we are done with all the usual sends, now we start streaming
    if streaming:
        await stream_messages_from_pipe(conversations)


async def action_accountmgmt() -> None:
    """Perform actions on account(s)."""
    try:
        # accountmgmt_action
        if gs.pa.add_account:
            action_add_account()
        if gs.pa.remove_account:
            action_remove_account()
        if gs.pa.get_enabled_accounts:
            action_get_enabled_accounts()
    except Exception as e:
        gs.log.error(
            "E256: "
            "Error during accountmgmt actions. "
            "Continuing despite error. "
            f"Exception: {e}"
        )
        gs.log.debug("Here is the traceback.\n" + traceback.format_exc())
        gs.err_count += 1


async def action_conversationsetget() -> None:
    """Perform conversation, get, set actions while being logged in."""
    if not gs.account:
        gs.log.error(
            "E214: " f"Account not set. Skipping action. {gs.__dict__}"
        )
        gs.err_count += 1
        return
    try:
        # conversation_action
        if gs.pa.add_conversation:
            action_add_conversation()
        if gs.pa.remove_conversation:
            action_remove_conversation()
        if gs.pa.add_conversation_member:
            action_add_conversation_member()
        if gs.pa.remove_conversation_member:
            action_remove_conversation_member()

        # set_action
        # if gs.pa.set_display_name:
        #     await action_set_display_name(gs..., gs...)

        # get_action
        if gs.pa.get_conversations:
            action_get_conversations()
        if gs.pa.get_conversation_members:
            action_get_conversation_members()
        # set action
        if gs.setget_action:
            gs.log.debug("Set or get action(s) were performed or attempted.")
    except Exception as e:
        gs.log.error(
            "E215: "
            "Error during conversation, set, get actions. "
            "Continuing despite error. "
            f"Exception: {e}"
        )
        gs.log.debug("Here is the traceback.\n" + traceback.format_exc())
        gs.err_count += 1


async def action_send() -> None:
    """Send messages while already logged in."""
    if not gs.account:
        gs.log.error("E218: " "Account not set. Skipping action.")
        gs.err_count += 1
        return
    try:
        gs.log.debug(f"account is: {gs.account}")
        # Now we can send messages and files
        # TODO
        await process_arguments_and_input(gs.pa.conversations)
        gs.log.debug("Message send action finished.")
    except Exception as e:
        gs.log.error(
            "E219: "
            "Error during sending. Continuing despite error. "
            f"Exception: {e}"
        )
        gs.err_count += 1


async def action_listen() -> None:
    """Listen to messages and files."""
    if not gs.account:
        gs.log.error("E164: " "Account not set. Skipping action.")
        gs.err_count += 1
        return
    try:
        gs.log.error(
            "Listening is not implemented yet. "
            "Please write a Pull Request to make it happen."
        )
        gs.err_count += 1
        # gs.log.debug(f"Listening type: {gs.pa.listen}")
        # if gs.pa.listen == FOREVER:
        #     await listen_forever(gs.client)
        # elif gs.pa.listen == ONCE:
        #     await listen_once(gs.client)
        #     # could use 'await listen_once_alternative(gs.client)'
        #     # as an alternative implementation
        # elif gs.pa.listen == TAIL:
        #     await listen_tail(gs.client, gs.credentials)
        # elif gs.pa.listen == ALL:
        #     await listen_all(gs.client, gs.credentials)
        # else:
        #     gs.log.error(
        #         "E165: "
        #         f'Unrecognized listening type "{gs.pa.listen}". '
        #         "Skipping listening."
        #     )
        #     gs.err_count += 1
    except Exception as e:
        gs.log.error(
            "E166: "
            "Error during listening. Continuing despite error. "
            f"Exception: {e}"
        )
        gs.log.debug("Here is the traceback.\n" + traceback.format_exc())
        gs.err_count += 1


def create_jami_controller() -> None:
    """Create the Jami controller object

    This enables us to communicate via the DBUS interface to the jamid daemon.
    """
    try:
        ctrl = libjamiCtrl(name=sys.argv[0], autoAnswer=False)
    except Exception as e:
        gs.log.error(
            "E234: "
            "Error during starting the Jami controller, "
            "that forms the API to DBUS. "
            "Did you install and run the 'jamid' daemon? "
            "Read the README.md file to learn how to install "
            "and run the 'jamid' daemon process. "
            f"Exception: {e}"
        )
        gs.err_count += 1
        try:
            gs.log.debug("Trying to automatically start jamid process.")
            subprocess.Popen(["/usr/libexec/jamid", "-p"])
            time.sleep(3)  # Sleep for 3 seconds
        except Exception as e:
            gs.log.error(
                "E234: "
                "Tried to automatically start jamid daemon, but failed. "
                "start jamid daemon process manually please. "
                f"Exception: {e}"
            )
            gs.err_count += 1
            raise e
        try:  # retry it for a second and last time
            ctrl = libjamiCtrl(name=sys.argv[0], autoAnswer=False)
        except Exception as e:
            raise e
    gs.ctrl = ctrl
    gs.log.debug(f"Jami controller object ctrl set. {gs.ctrl.__dict__}")


def action_account() -> None:
    """Set the accountid.

    Sets the global accountid or raises an exception to quit program.
    Sets gs.account  (not gs.pa.account)
    """
    if gs.account is not None:
        # alread set
        return
    accts = gs.ctrl.getAllEnabledAccounts()
    for acct in accts:
        details = gs.ctrl.getAccountDetails(acct)
        gs.log.debug(f"Account details: {details}")

    if gs.pa.account is None:
        gs.log.debug(
            "No account specified in command line. --account not used."
        )
        # get all accounts
        # if there is exactly 1, then use it
        # otherwise raise error
        if len(accts) == 0:
            txt = "E234: " "No account found. Create an account first. "
            gs.err_count += 1
            raise JamiCommanderError(txt)
        elif len(accts) == 1:
            gs.pa.account = accts[0]
            gs.account = accts[0]
            gs.log.debug(
                f"Exactly one valid account found: {gs.account}. "
                "It will be used."
            )
        else:
            txt = (
                "E234: "
                "More than one account found. Cannot decide which one. "
                "Specify an account by using --account. "
                f"Valid accountids are {accts}."
            )
            gs.err_count += 1
            raise JamiCommanderError(txt)
    else:
        gs.log.debug(
            f"Account {gs.pa.account} was specified in command line. "
            "--account was used."
        )
        # check if account is valid
        # otherwise raise error
        if gs.pa.account not in accts:
            txt = (
                "E234: "
                "Account is not a valid accountid. "
                "Specify correct accountid with --account. "
                f"Valid accountids are {accts}."
            )
            gs.err_count += 1
            raise JamiCommanderError(txt)
    gs.account = gs.pa.account
    gs.log.debug(f"Account {gs.account} is valid and will be used.")


async def async_main() -> None:
    """Run main functions being inside the event loop."""
    # Todo: cleanup
    # login explicitly
    # login implicitly
    # verify
    # set, get, conversation,
    # send
    # listen
    # logout
    # close session
    # sys.argv ordering? # todo
    try:
        create_jami_controller()
        gs.log.debug("In function async_main().")
        if gs.accountmgmt_action:
            # do NOT set the account value --account
            await action_accountmgmt()
        if gs.conversation_action or gs.setget_action:
            action_account()  # set the account value --account
            await action_conversationsetget()
        if gs.send_action:
            action_account()  # set the account value --account
            await action_send()
        # if gs.pa.room_invites and gs.pa.listen not in (FOREVER, ONCE):
        #    action_account() # set the account value --account
        #     await listen_invites_once(gs....)
        if gs.listen_action:
            action_account()  # set the account value --account
            await action_listen()
        # if gs.pa.logout:
        #     await action_logout()
    except Exception:
        raise
    finally:
        # clean up DBUS API connection
        gs.log.debug("Leaving DBUS session, no cleanup necessary.")


def check_arg_files_readable() -> None:
    """Check if files from command line are readable."""
    arg_files = gs.pa.file if gs.pa.file else []
    r = True
    errtxt = (
        "E236: "
        "These files specified in the command line were not found "
        "or are not readable: "
    )
    for fn in arg_files:
        if (fn != "-") and not (isfile(fn) and access(fn, R_OK)):
            if not r:
                errtxt += ", "
            errtxt += f'"{fn}"'
            r = False
            errfile = fn
    if not r:
        raise FileNotFoundError(errno.ENOENT, errtxt, errfile)


def check_download_media_dir() -> None:
    """Check if media download directory is correct."""
    if not gs.pa.download_media:
        return  # "": that means no download of media, valid value
    # normailzed for humans
    dl = os.path.normpath(gs.pa.download_media)
    gs.pa.download_media = dl
    if os.path.isfile(dl):
        raise NotADirectoryError(
            errno.ENOTDIR,
            "E237: "
            f'"{dl}" cannot be used as media directory, because '
            f'"{dl}" is a file. Specify a different directory for downloading '
            "media.",
            dl,
        )
    if os.path.isdir(dl):
        if os.access(dl, os.W_OK):  # Check for write access
            return  # all OK
        else:
            raise PermissionError(
                errno.EPERM,
                "E238: "
                "Found an existing media download directory "
                f'"{dl}". But this directory is lacking write '
                "permissions. Add write permissions to it.",
                dl,
            )
    else:
        # not a file, not a directory, create directory
        mode = 0o777
        try:
            os.mkdir(dl, mode)
        except OSError as e:
            raise OSError(
                e.errno,
                "E239: "
                "Could not create media download directory "
                f"{dl} for you. ({e})",
                dl,
            )
        gs.log.debug(f'Created media download directory "{dl}" for you.')


def check_version() -> None:
    """Check if latest version."""
    pkg = PROG_WITHOUT_EXT
    ver = VERSIONNR  # default, fallback
    try:
        ver_pip = metadata.version(pkg)  # from installed pip package
    except Exception as e:
        gs.log.debug(
            f"Failed to get version from meta-data of pip package {pkg}. "
            f"Exception {e}"
        )
        pass  # if installed via git clone, package will not exists
    else:
        if ver_pip != ver:
            gs.log.info(
                f"Looks like you have 2 versions of {pkg} installed. "
                f"One version via pip with version number {ver_pip}. "
                f"And another version outside of pip with version {ver}. "
                "You are currently executing the version outside of pip "
                f"with version number {ver}. We advise you on whether to "
                "upgrade the version you are currently running."
            )
    gs.log.debug(f"Version of currently executed package {pkg} is {ver}.")

    installed_version = LooseVersion(ver)
    # fetch package metadata from PyPI
    pypi_url = f"https://pypi.org/pypi/{pkg}/json"
    gs.log.debug(f"getting version data from URL {pypi_url}")
    try:
        response = urllib.request.urlopen(pypi_url).read().decode()
    except Exception as e:
        gs.log.warning(
            "Could not obtain version info from " f"{pypi_url} for you. ({e})"
        )
        latest_version = "unknown"
        utd = "Try again later."
    else:
        latest_version = max(
            LooseVersion(s) for s in json.loads(response)["releases"].keys()
        )
        if installed_version >= latest_version:
            utd = "You are up-to-date!"
        else:
            utd = "Consider updating!"
    version_info = (
        f"package: {pkg}, running: {installed_version}, "
        f"latest: {latest_version} ==> {utd}"
    )
    gs.log.debug(version_info)
    # output format controlled via --output flag
    text = version_info
    json_ = {
        "package": f"{pkg}",
        "version_running": f"{installed_version}",
        "version_latest": f"{latest_version}",
        "comment": f"{utd}",
    }
    # json_.pop("key")
    print_output(
        gs.pa.output,
        text=text,
        json_=json_,
    )


def version() -> None:
    """Print version info."""
    python_version = sys.version
    python_version_nr = (
        str(sys.version_info.major)
        + "."
        + str(sys.version_info.minor)
        + "."
        + str(sys.version_info.micro)
    )
    version_info = (
        "\n"
        f"  _|_|_|_|_|      _|_|_|    _|       {PROG_WITHOUT_EXT}: "
        f"{VERSIONNR} {VERSION}\n"
        "          _|    _|            _|     a Jami CLI client\n"
        "          _|    _|              _|   enjoy and submit PRs\n"
        f"  _|      _|    _|            _|     Python: {python_version_nr}\n"
        f"    _|_|_|        _|_|_|    _|       "
        "https://github.com/8go/jami-commander\n"
        "\n"
    )
    gs.log.debug(version_info)
    # output format controlled via --output flag
    text = version_info
    json_ = {
        f"{PROG_WITHOUT_EXT}": {
            "version": f"{VERSIONNR}",
            "date": f"{VERSION}",
        },
        "python": {
            "version": f"{python_version_nr}",
            "info": f"{python_version}",
        },
    }
    # json_.update({"key": value})  # add dict items
    # json_.pop("key")
    print_output(
        gs.pa.output,
        text=text,
        json_=json_,
    )


def initial_check_of_log_args() -> None:
    """Check logging related arguments.

    Arguments:
    ---------
    None

    Returns: None

    Raises exception on error.
    """
    if not gs.pa.log_level:
        return  # all OK
    for i in range(len(gs.pa.log_level)):
        up = gs.pa.log_level[i].upper()
        gs.pa.log_level[i] = up
        if up not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            # gs.err_count += 1  # wrong
            raise JamiCommanderError(
                "E241: "
                '--log-level only allows values "DEBUG", "INFO", "WARNING", '
                '"ERROR", or "CRITICAL". --log-level argument incorrect. '
                f"({up})"
            ) from None


# according to pylama: function too complex: C901 # noqa: C901
def initial_check_of_args() -> None:  # noqa: C901
    """Check arguments."""
    # First, the adjustments
    gs.log.debug("Todo: initial_check_of_args() needs to be implemented")

    if gs.pa.output is not None:
        gs.pa.output = gs.pa.output.lower()

    # accountmgmt
    if gs.pa.add_account or gs.pa.remove_account or gs.pa.get_enabled_accounts:
        gs.accountmgmt_action = True
    else:
        gs.accountmgmt_action = False

    # conversation
    if (
        gs.pa.add_conversation
        or gs.pa.remove_conversation
        or gs.pa.add_conversation_member
        or gs.pa.remove_conversation_member
    ):
        gs.conversation_action = True
    else:
        gs.conversation_action = False

    # send
    if gs.pa.message or gs.pa.file:
        gs.send_action = True
    else:
        gs.send_action = False

    # get
    if gs.pa.get_conversations or gs.pa.get_conversation_members:
        gs.get_action = True
    else:
        gs.get_action = False

    # set
    if gs.set_action or gs.get_action:
        gs.setget_action = True
    else:
        gs.setget_action = False

    # how often is "-" used to represent stdin
    # must be 0 or 1; cannot be used twice or more
    STDIN_MESSAGE = 0
    STDIN_FILE = 0
    STDIN_TOTAL = 0
    if gs.pa.file:
        for file in gs.pa.file:
            if file == "-":
                STDIN_FILE += 1
                gs.stdin_use = "file"
    if gs.pa.message:
        for message in gs.pa.message:
            if message == "-" or message == "_":
                STDIN_MESSAGE += 1
                gs.stdin_use = "message"
    STDIN_TOTAL = STDIN_MESSAGE + STDIN_FILE

    # Secondly, the checks
    if gs.pa.version and (
        gs.pa.version.lower() != PRINT and gs.pa.version.lower() != CHECK
    ):
        t = (
            f'For --version currently only "{PRINT}" '
            f'or "{CHECK}" is allowed as keyword.'
        )
    elif gs.pa.account is not None and (gs.pa.account.strip() == ""):
        t = "Don't use an empty name for --account."
    elif gs.pa.output not in (
        OUTPUT_TEXT,
        OUTPUT_JSON,
    ):
        t = (
            "Incorrect value given for --output. "
            f"Only '{OUTPUT_TEXT}' and '{OUTPUT_JSON}' are allowed."
        )
    elif STDIN_TOTAL > 1:
        t = (
            'The character "-" is used more than once '
            'to represent "stdin" for piping information '
            f'into "{PROG_WITHOUT_EXT}". Stdin pipe can '
            "be used at most once."
        )
    else:
        gs.log.debug("All arguments are valid. All checks passed.")
        return  # all OK
    # gs.err_count += 1 # do not increment for JamiCommanderError
    raise JamiCommanderError("E240: " + t) from None


class colors:
    """Colors class.

    reset all colors with colors.reset.
    2 sub classes: fg for foreground and bg for background;
    use as colors.subclass.colorname.
    i.e. colors.fg.red or colors.bg.green
    also, the generic bold, disable, underline, reverse, strike through,
    and invisible work with the main class i.e. colors.bold

    use like this:
    print(colors.bg.green, "SKk", colors.fg.red, "Amartya")
    print(colors.bg.lightgrey, "SKk", colors.fg.red, "Amartya")
    """

    reset = "\033[0m"
    bold = "\033[01m"
    disable = "\033[02m"
    inverse = "\033[03m"
    underline = "\033[04m"
    blink = "\033[05m"
    blink2 = "\033[06m"
    reverse = "\033[07m"
    invisible = "\033[08m"
    strikethrough = "\033[09m"

    class fg:
        black = "\033[30m"
        red = "\033[31m"
        green = "\033[32m"
        orange = "\033[33m"
        blue = "\033[34m"
        purple = "\033[35m"
        cyan = "\033[36m"
        lightgrey = "\033[37m"
        darkgrey = "\033[90m"
        lightred = "\033[91m"
        lightgreen = "\033[92m"
        yellow = "\033[93m"
        lightblue = "\033[94m"
        pink = "\033[95m"
        lightcyan = "\033[96m"

    class bg:
        black = "\033[40m"
        red = "\033[41m"
        green = "\033[42m"
        orange = "\033[43m"
        blue = "\033[44m"
        purple = "\033[45m"
        cyan = "\033[46m"
        lightgrey = "\033[47m"


# according to linter: function is too complex, C901
def main_inner(
    argv: Union[None, list] = None
) -> None:  # noqa: C901 # ignore mccabe if-too-complex
    """Run the program.

    Function signature identical to main().
    Please see main().

    Returns None. Returns nothing.

    Raises exception if an error is detected. Many exceptions are
        possible. One of them is: JamiCommanderError.
        Sets global state to communicate errors.

    """
    if argv:
        sys.argv = argv
    # prepare the global state
    global gs
    gs = GlobalState()
    global SEP
    # Construct the argument parser
    ap = argparse.ArgumentParser(
        add_help=False,
        description=(f"Welcome to {PROG_WITHOUT_EXT}, a Jami CLI client. "),
        epilog="You are running "
        f"version {VERSIONNR} {VERSION}. Enjoy, star on Github and "
        "contribute by submitting a Pull Request.",
    )
    # -h, see add_help=False
    ap.add_argument(
        # see script create help.help.txt
        # help string up to but excluding "Details::" is used for
        # (short) `--help`. The full text will be used for long `--manual`.
        "--usage",
        required=False,
        action="store_true",
        help="Print usage. "
        "Details:: See also --help for printing a bit more and --manual "
        "for printing a lot more detailed information.",
    )
    # -h, see add_help=False
    ap.add_argument(
        "-h",
        "--help",
        required=False,
        action="store_true",
        help="Print help. "
        "Details:: See also --usage for printing even less information, "
        "and --manual for printing more detailed information.",
    )
    # see -h, see add_help=False
    ap.add_argument(
        "--manual",
        required=False,
        action="store_true",
        help="Print manual. "
        "Details:: See also --usage for printing the absolute minimum, "
        "and --help for printing less.",
    )
    # see -h, see add_help=False
    ap.add_argument(
        "--readme",
        required=False,
        action="store_true",
        help="Print README.md file. "
        "Details:: Tries to print the local README.md file from installation. "
        "If not found it will get the README.md file from github.com and "
        "print it. See also --usage, --help, and --manual.",
    )
    # Add the arguments to the parser
    ap.add_argument(
        "-d",
        "--debug",
        action="count",
        default=0,
        help="Print debug information. "
        "Details:: If used once, only the log level of "
        f"{PROG_WITHOUT_EXT} is set to DEBUG. "
        'If used twice ("-d -d" or "-dd") then '
        f"log levels of both {PROG_WITHOUT_EXT} and underlying modules are "
        'set to DEBUG. "-d" is a shortcut for "--log-level DEBUG". '
        'See also --log-level. "-d" takes precedence over "--log-level". '
        'Additionally, have a look also at the option "--verbose". ',
    )
    ap.add_argument(
        "--log-level",
        required=False,
        action="extend",
        nargs="+",
        type=str,
        metavar=("DEBUG|INFO|WARNING|ERROR|CRITICAL"),
        help="Set the log level(s). "
        "Details:: Possible values are "
        '"DEBUG", "INFO", "WARNING", "ERROR", and "CRITICAL". '
        "If --log_level is used with one level argument, only the log level "
        f"of {PROG_WITHOUT_EXT} is set to the specified value. "
        "If --log_level is used with two level argument "
        '(e.g. "--log-level WARNING ERROR") then '
        f"log levels of both {PROG_WITHOUT_EXT} and underlying modules are "
        "set to the specified values. "
        "See also --debug.",
    )
    ap.add_argument(
        "--verbose",
        action="count",
        default=0,
        help="Set the verbosity level. "
        "Details:: If not used, then verbosity will be "
        "set to low. If used once, verbosity will be high. "
        "If used more than once, verbosity will be very high. "
        "Verbosity only affects the debug information. "
        "So, if '--debug' is not used then '--verbose' will be ignored.",
    )

    ap.add_argument(
        "--get-enabled-accounts",
        required=False,
        action="store_true",
        help="List all enabled accounts by ids. "
        "Details:: Prints all enabled account ids.",
    )

    ap.add_argument(
        "--add-account",
        required=False,
        action="extend",
        nargs=4,
        type=str,
        metavar=("ALIAS", "HOSTNAME", "USERNAME", "PASSWORD"),
        help="Add a new Jami account. "
        "Details:: You can add, i.e. create, as many accounts as you wish. "
        "An account will be identified by an account id, "
        "a long random looking hexadecial string. "
        'Provide 4 values, each one can be set to empty string "" '
        "if desired.",
    )

    ap.add_argument(
        "--remove-account",
        required=False,
        action="extend",
        nargs="+",
        type=str,
        metavar="ACCOUNTID",
        help="Remove a Jami account. "
        "Details:: Specify one or multiple accounts by id to be removed. ",
    )

    ap.add_argument(
        "--get-conversations",
        required=False,
        action="store_true",
        help="List all swarm conversations by ids. "
        "Details:: Prints all swarm conversations ids "
        "associated with the account in --account or "
        "the automatically chosen account.",
    )

    ap.add_argument(
        "--add-conversation",
        required=False,
        action="store_true",
        help="Add a conversation to an account. "
        "Details:: You can add, i.e. create, as many swarm conversation "
        "as you wish. "
        "A swarm conversation will be identified by an conversation id, "
        "a long random looking hexadecial string. "
        "The conversation is associated with the account in --account.",
    )

    ap.add_argument(
        "--remove-conversation",
        required=False,
        action="store_true",
        help="Remove one or multiple conversations from an account. "
        "Details:: Specify one or multiple accounts by id to be removed "
        "in the --conversations argument. ",
    )

    ap.add_argument(
        "--get-conversation-members",
        required=False,
        action="store_true",
        help="List all members of one or multiple swarm conversations by ids. "
        "Details:: Prints all members of the swarm conversations "
        "specified with --conversations. "
        "They must be associated with the account in --account or "
        "the automatically chosen account.",
    )

    ap.add_argument(
        "--add-conversation-member",
        required=False,
        action="extend",
        nargs="+",
        type=str,
        metavar="USERID",
        help="Add member(s) to one or multiple swarm conversations. "
        "Details:: You can add one or multple members to "
        "one or multiple conversations of the same account. "
        "Members are specified with --add-conversation-member. "
        "Conversations are specified with --conversations. "
        "A swarm conversation will be identified by an conversation id, "
        "a long random looking hexadecial string. "
        "The conversations are associated with the account in --account.",
    )

    ap.add_argument(
        "--remove-conversation-member",
        required=False,
        action="extend",
        nargs="+",
        type=str,
        metavar="USERID",
        help="Remove member(s) from one or multiple swarm conversations. "
        "Details:: You can remove one or multple members from "
        "one or multiple conversations of the same account. "
        "Members are specified with --add-conversation-member. "
        "Conversations are specified with --conversations. "
        "A swarm conversation will be identified by an conversation id, "
        "a long random looking hexadecial string. "
        "The conversations are associated with the account in --account.",
    )

    ap.add_argument(
        "-a",
        "--account",
        required=False,
        type=str,  # accountid
        metavar="ACCOUNTID",
        help="Connect to and use the specified account. "
        "Details:: This requires exactly one argument, the account id. "
        "This is not the user name but the long random looking "
        "string made up of hexadecimal digits. "
        "If --account is not used then {PROG_WITHOUT_EXT} will "
        "try to automatically detect and use an enabled account. "
        "To be used by arguments like --message and -file. ",
    )

    ap.add_argument(
        "-c",
        "--conversations",
        required=False,
        action="extend",
        nargs="+",
        type=str,
        metavar="CONVERSATIONID",
        help="Specify one or multiple swarm conversations. "
        "Details:: Optionally specify one or multiple swarm conversations "
        "via swarm ids (conversation ids). "
        "Swarm ids are long random looking hexadecial strings. "
        "--conversations is used by various send actions and "
        "various listen actions. "
        "The chosen account must have access to the specified conversations "
        "in order to send messages there or listen on the conversations. "
        "Messages cannot be sent to arbitrary conversations."
        "This is used in --message, --file, --remove-conversation, "
        "--get-conversation-members, --add-conversation-members, "
        "--remove-conversation-member.",
    )

    # allow multiple messages , e.g. -m "m1" "m2" or -m "m1" -m "m2"
    # message is going to be a list of strings
    # e.g. message=[ 'm1', 'm2' ]
    ap.add_argument(
        "-m",
        "--message",
        required=False,
        action="extend",
        nargs="+",
        type=str,
        metavar="TEXT",
        help="Send one or multiple text messages. "
        "Details:: Message data must not be binary data, it "
        "must be text. If no '-m' is used and no other conflicting "
        "arguments are provided, and information is piped into the program, "
        "then the piped data will be used as message. "
        "Finally, if there are no operations at all in the arguments, then "
        "a message will be read from stdin, i.e. from the keyboard. "
        "This option can be used multiple times to send "
        "multiple messages. If there is data piped "
        "into this program, then first data from the "
        "pipe is published, then messages from this "
        "option are published. Messages will be sent last, "
        "i.e. after objects like files. "
        "Input piped via stdin can additionally be specified with the "
        "special character '-'. "
        f"If you want to feed a text message into {PROG_WITHOUT_EXT} "
        "via a pipe, via stdin, then specify the special "
        "character '-'. If '-' is specified as message, "
        "then the program will read the message from stdin. "
        "With '-' the whole message, all lines, will be considered "
        "a single message and sent as one message. "
        "If your message is literally '-' then use '\\-' "
        "as message in the argument. "
        "'-' may appear in any position, i.e. '-m \"start\" - \"end\"' "
        "will send 3 messages out of which the second one is read from stdin. "
        "'-' may appear only once overall in all arguments. "
        "Similar to '-', another shortcut character is '_'. The "
        "special character '_' is used for streaming data via "
        "a pipe on stdin. With '_' the stdin pipe is read line-by-line "
        "and each line is treated as a separate message and sent right "
        "away. The program waits for pipe input until the pipe is "
        "closed. E.g. Imagine a tool that generates output sporadically "
        f"24x7. It can be piped, i.e. streamed, into {PROG_WITHOUT_EXT}, and "
        f"{PROG_WITHOUT_EXT} stays active, sending all input instantly. "
        "If you want to send the literal letter '_' then escape it "
        "and send '\\_'. "
        "'_' can be used only once. And either '-' or '_' can be used. "
        "See also --conversations. ",
    )

    # allow multiple files , e.g. -f "a1.pdf" "a2.doc"
    # or -f "a1.pdf" -f "a2.doc"
    # file is going to be a list of strings
    # e.g. file=[ 'a1.pdf', 'a2.doc' ]
    ap.add_argument(
        "-f",
        "--file",
        required=False,
        action="extend",
        nargs="+",
        type=str,
        metavar="FILE",
        help="Send one or multiple files (e.g. PDF, DOC, MP4). "
        "Details:: This option can be used multiple times to send "
        "multiple files. First files are sent, "
        "then text messages are sent. "
        f"If you want to feed a file into {PROG_WITHOUT_EXT} "
        "via a pipe, via stdin, then specify the special "
        "character '-'. See description of '-m' to see how '-' is handled. "
        "See also --conversations. ",
    )

    # -h already used for --help, -w for "web"
    ap.add_argument(
        "-w",
        "--html",
        required=False,
        action="store_true",
        help='Send message as format "HTML". '
        "Details:: If not specified, message will be sent "
        'as format "TEXT". E.g. that allows some text '
        "to be bold, etc. Currently no HTML tags are "
        "accepted by Jami.",
    )
    # -m already used for --message, -z because there were no letters left
    ap.add_argument(
        "-z",
        "--markdown",
        required=False,
        action="store_true",
        help='Send message as format "MARKDOWN". '
        "Details:: If not specified, message will be sent "
        'as format "TEXT". E.g. that allows sending of text '
        "formatted in MarkDown language.",
    )
    #  -c is already used for --credentials, -k as it sounds like c
    ap.add_argument(
        "-k",
        "--code",
        required=False,
        action="store_true",
        help='Send message as format "CODE". '
        "Details:: If not specified, message will be sent "
        'as format "TEXT". If both --html and --code are '
        "specified then --code takes priority. This is "
        "useful for sending ASCII-art or tabbed output "
        "like tables as a fixed-sized font will be used "
        "for display.",
    )
    #  -j for emoJize
    ap.add_argument(
        "-j",
        "--emojize",
        required=False,
        action="store_true",
        help="Send message after emojizing. "
        "Details:: If not specified, message will be sent "
        'as format "TEXT". If both --code and --emojize are '
        "specified then --code takes priority. This is "
        "useful for sending emojis in shortcode form :collision:.",
    )

    ap.add_argument(
        "--split",
        required=False,
        type=str,
        metavar="SEPARATOR",
        help="Split message text into multiple Jami messages. "
        "Details:: If set, split the message(s) into multiple messages "
        "wherever the string specified with --split occurs. "
        "E.g. One pipes a stream of RSS articles into the "
        "program and the articles are separated by three "
        "newlines. "
        'Then with --split set to "\\n\\n\\n" each article '
        "will be printed in a separate message. "
        "By default, i.e. if not set, no messages will be split.",
    )

    ap.add_argument(
        "--separator",
        required=False,
        type=str,
        default=DEFAULT_SEPARATOR,  # defaults to SEP if not used
        # Text is scanned and repeated spaces are removes, so "    "
        # or {DEFAULT_SEPARATOR} will be truncated to " ". Hence "4 spaces"
        metavar="SEPARATOR",
        help="Set a custom separator used for certain print outs. "
        "Details:: By default, i.e. if --separator is not used, "
        "4 spaces are used as "
        "separator between columns in print statements. You could set "
        "it to '\\t' if you prefer a tab, but tabs are usually replaced "
        "with spaces by the terminal. So, that might not give you what you "
        "want. Maybe ' || ' is an alternative choice.",
    )

    ap.add_argument(
        "-o",
        "--output",
        required=False,
        type=str,  # output method: text, json
        default=OUTPUT_DEFAULT,  # when --output is not used
        metavar="TEXT|JSON",
        help="Select an output format. "
        "Details:: This option decides on how the output is presented. "
        f"Currently offered choices are: '{OUTPUT_TEXT}' and '{OUTPUT_JSON}'. "
        "Provide one of these choices. "
        f"The default is '{OUTPUT_DEFAULT}'. If you want to use the default, "
        "then there is no need to use this option. "
        f"If you have chosen '{OUTPUT_TEXT}', "
        "the output will be formatted with the intention to be "
        "consumed by humans, i.e. readable text. "
        f"If you have chosen '{OUTPUT_JSON}', "
        "the output will be formatted as JSON. "
        "The content of the JSON object matches the data provided by the "
        "Jami API. In some occasions the output is enhanced "
        "by having a few extra data items added for convenience. "
        "In most cases the output will be processed by other programs "
        "rather than read by humans.",
    )

    ap.add_argument(
        "-v",
        "-V",
        "--version",
        required=False,
        type=str,
        default=VERSION_UNUSED_DEFAULT,  # when -t is not used
        nargs="?",  # makes the word optional
        # when -v is used, but text is not added
        const=VERSION_USED_DEFAULT,
        metavar="PRINT|CHECK",
        help="Print version information or check for updates. "
        "Details:: This option takes zero or one argument. "
        f"If no argument is given, '{PRINT}' is assumed which will "
        f"print the version of the currently installed 'PROG_WITHOUT_EXT' "
        f"package. '{CHECK}' is the alternative. "
        "'{CHECK}' connects to https://pypi.org and gets the version "
        "number of latest stable release. There is no 'calling home' "
        "on every run, only a 'check pypi.org' upon request. Your "
        "privacy is protected. The new release is neither downloaded, "
        "nor installed. It just informs you. "
        "After printing version information the "
        "program will continue to run. This is useful for having version "
        "number in the log files.",
    )
    gs.pa = ap.parse_args()
    # wrap and indent: https://towardsdatascience.com/6-fancy-built-in-text-
    #                  wrapping-techniques-in-python-a78cc57c2566
    # if output is not TTY, then don't add colors, e.g. when output is piped
    if sys.stdout.isatty():
        # You're running in a real terminal
        # colors
        # adapt width
        term_width = os.get_terminal_size()[0]
        # print("terminal width ", term_width)
        con = colors.fg.green
        coff = colors.reset
        eon = colors.bold + con
        eoff = colors.reset + con
    else:
        # You're being piped or redirected
        # no Colors
        # width = 80
        term_width = 80
        # print("not in terminal, using default terminal width ", term_width)
        con = ""
        coff = ""
        eon = ""
        eoff = ""
    if gs.pa.usage:
        print(textwrap.fill(ap.description, width=term_width))
        print("")
        ap.print_usage()
        print("")
        print(textwrap.fill(ap.epilog, width=term_width))
        return 0
    if gs.pa.help:
        print(textwrap.fill(ap.description, width=term_width))
        print("")
        print(
            textwrap.fill(
                f"{PROG_WITHOUT_EXT} supports these arguments:",
                width=term_width,
            )
        )
        # print("")
        help_help_pre = """
<--usage>
Print usage.
<-h>, <--help>
Print help.
<--manual>
Print manual.
<--readme>
Print README.md file.
<-d>, <--debug>
Print debug information.
<--log-level> DEBUG|INFO|WARNING|ERROR|CRITICAL [DEBUG|INFO|WARNING|ERROR|CRITICAL ...]
Set the log level(s).
<--verbose>
Set the verbosity level.
<--get-enabled-accounts>
List all enabled accounts by ids.
<--add-account> ALIAS HOSTNAME USERNAME PASSWORD
Add a new Jami account.
<--remove-account> ACCOUNTID [ACCOUNTID ...]
Remove a Jami account.
<--get-conversations>
List all swarm conversations by ids.
<--add-conversation>
Add a conversation to an account.
<--remove-conversation>
Remove one or multiple conversations from an account.
<--get-conversation-members>
List all members of one or multiple swarm conversations by ids.
<--add-conversation-member> USERID [USERID ...]
Add member(s) to one or multiple swarm conversations.
<--remove-conversation-member> USERID [USERID ...]
Remove member(s) from one or multiple swarm conversations.
<-a> ACCOUNTID, <--account> ACCOUNTID
Connect to and use the specified account.
<-c> CONVERSATIONID [CONVERSATIONID ...], <--conversations> CONVERSATIONID [CONVERSATIONID ...]
Specify one or multiple swarm conversations.
<-m> TEXT [TEXT ...], <--message> TEXT [TEXT ...]
Send one or multiple text messages.
<-f> FILE [FILE ...], <--file> FILE [FILE ...]
Send one or multiple files (e.g. PDF, DOC, MP4).
<-w>, <--html>
Send message as format "HTML".
<-z>, <--markdown>
Send message as format "MARKDOWN".
<-k>, <--code>
Send message as format "CODE".
<-j>, <--emojize>
Send message after emojizing.
<--split> SEPARATOR
Split message text into multiple Jami messages.
<--separator> SEPARATOR
Set a custom separator used for certain print outs.
<-o> TEXT|JSON, <--output> TEXT|JSON
Select an output format.
<-v> [PRINT|CHECK], -V [PRINT|CHECK], <--version> [PRINT|CHECK]
Print version information or check for updates.
""".replace(
            "<", eon
        ).replace(
            ">", eoff
        )
        header = False  # first line is newline
        for line in help_help_pre.split("\n"):
            if header:
                print(
                    textwrap.fill(con + line + coff, width=term_width),
                    flush=True,
                )
            else:
                print(
                    textwrap.indent(
                        textwrap.fill(line, width=term_width - 2), "  "
                    ),
                    flush=True,
                )

            header = not header
        # print("")
        print(textwrap.fill(ap.epilog, width=term_width))
        return 0
    if gs.pa.manual:
        description = (
            f"Welcome to {PROG_WITHOUT_EXT}, a Jami CLI client. ─── "
            "This program implements a simple Jami CLI "
            "client that can send messages, etc. "
            "It can send one or multiple message to one or "
            "multiple Jami conversations. "
            "Arbitrary files can be sent as well. "
            "Listen and receiving is not yet implemented. "
            "Please write a PR for listening. "
            "End-to-end encryption is enabled by default "
            "and cannot be turned off.  ─── "
            "Bundling several actions together into a single call to "
            f"{PROG_WITHOUT_EXT} is faster than calling {PROG_WITHOUT_EXT} "
            "multiple times with only one action. If there are both 'set' "
            "and 'get' actions present in the arguments, then the 'set' "
            "actions will be performed before the 'get' actions. Then "
            "send actions and at the very end listen actions will be "
            "performed. ─── "
            "For even more explications and examples also read the "
            "documentation provided in the on-line Github README.md file "
            "or the README.md in your local installation.  ─── "
            "For less information just use --help instead of --manual."
        )
        print(textwrap.fill(description, width=term_width), flush=True)
        print("")
        ap.print_help(file=None)  # ap.print_usage() is included
        return 0
    if gs.pa.readme:
        # Todo
        exedir = os.path.dirname(os.path.realpath(__file__))
        readme = exedir + "/../" + "README.md"
        readme_primary = readme
        foundpath = None
        if os.path.exists(readme):
            foundpath = readme
            print(f"Found local README.md here: {readme}")
        else:
            readme = exedir + "/" + "README.md"
            if os.path.exists(readme):
                foundpath = readme
                print(f"Found local README.md here: {readme}")
        if foundpath is None:
            print(
                "Sorry, README.md not found locally "
                f"in installation directory {readme_primary}."
            )
            print(f"Hence downloading it from {README_FILE_RAW_URL}.")
            notused, foundpath = tempfile.mkstemp()
            urllib.request.urlretrieve(README_FILE_RAW_URL, foundpath)
        try:
            with open(foundpath, "r+") as f:
                text = f.read()
            print(f"{text}")
        except Exception:  # (BrokenPipeError, IOError):
            # print("BrokenPipeError caught", file=sys.stderr)
            pass
        return 0

    logging.basicConfig(  # initialize root logger, a must
        format="{asctime}: {levelname:>8}: {name:>16}: {message}", style="{"
    )
    # set log level on root
    if "DEBUG" in os.environ:
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.INFO)

    gs.log = logging.getLogger(PROG_WITHOUT_EXT)

    if gs.pa.log_level:
        initial_check_of_log_args()
        if len(gs.pa.log_level) > 0:
            if len(gs.pa.log_level) > 1:
                # set log level for EVERYTHING
                logging.getLogger().setLevel(gs.pa.log_level[1])
            # set log level for jami-commander
            gs.log.setLevel(gs.pa.log_level[0])
            gs.log.debug(
                f"Log level is set for module {PROG_WITHOUT_EXT}. "
                f"log_level={gs.pa.log_level[0]}"
            )
            if len(gs.pa.log_level) > 1:
                # only now that local log level is set, we can log prev. info
                gs.log.debug(
                    f"Log level is set for modules below {PROG_WITHOUT_EXT}. "
                    f"log_level={gs.pa.log_level[1]}"
                )
    if gs.pa.debug > 0:
        if gs.pa.debug > 1:
            # turn on debug logging for EVERYTHING
            logging.getLogger().setLevel(logging.DEBUG)
        # turn on debug logging for jami-commander
        gs.log.setLevel(logging.DEBUG)
        gs.log.debug(f"Debug is turned on. debug count={gs.pa.debug}")
        if gs.pa.log_level and len(gs.pa.log_level) > 0:
            gs.log.warning(
                "W111: " "Debug option -d overwrote option --log-level."
            )
            gs.warn_count += 1

    SEP = bytes(gs.pa.separator, "utf-8").decode("unicode_escape")
    gs.log.debug(
        f'Separator is set to "{SEP}" of '
        f"length {len(SEP)}. E.g. Col1{SEP}Col2."
    )
    initial_check_of_args()
    # Todo: check_download_media_dir()
    try:
        check_arg_files_readable()
    except Exception as e:
        gs.log.error(e)  # already has Exxx: unique error number
        raise JamiCommanderError(
            f"{PROG_WITHOUT_EXT} forces an early abort. "
            "To avoid partial execution, no action has been performed at all. "
            "Nothing has been sent. Fix your arguments and run the command "
            "again."
        ) from None

    if gs.pa.version:
        if gs.pa.version.lower() == PRINT:
            version()  # continue execution
        else:
            check_version()  # continue execution
        if not (
            gs.send_action
            # todo
            or gs.accountmgmt_action
            or gs.conversation_action
            or gs.listen_action
            # or gs.pa.listen != LISTEN_DEFAULT
            # or gs.pa.tail != TAIL_UNUSED_DEFAULT
            # or gs.pa.verify
            or gs.setget_action
        ):
            gs.log.debug("Only --version. Print and quit.")
            return  # just version, quit

    create_pid_file()

    gs.log.debug(f'Python version is "{sys.version}"')
    gs.log.debug(f'Stdin pipe is assigned to "{gs.stdin_use}".')

    try:
        asyncio.run(async_main())  # do everything in the event loop
        # the next can be reached on success or failure
        gs.log.debug(f"The program {PROG_WITH_EXT} left the event loop.")
    except TimeoutError as e:
        gs.err_count += 1
        raise JamiCommanderError(
            "E247: "
            f"The program {PROG_WITH_EXT} ran into a timeout. "
            "Most likely connectivity to internet was lost. "
            "If this happens frequently consider running this "
            "program as a service so it will restart automatically. Sorry."
        ) from e
    except JamiCommanderError:
        raise
    except KeyboardInterrupt:
        gs.log.debug("Keyboard interrupt received.")
    except Exception:
        gs.err_count += 1
        gs.log.error("E248: " f"The program {PROG_WITH_EXT} failed. Sorry.")
        raise
    finally:
        cleanup()


def main(argv: Union[None, list] = None) -> int:
    """Run the program.

    main() is an entry point allowing other Python programs to
    easily call jami-commander.

    Arguments:
    ---------
    argv : list of arguments as in sys.argv; first element is the
        program name, further elements are the arguments; every
        element must be of type "str".
        argv is optional and can be None.
        If argv is set then these arguments will be used as arguments for
        jami-commander. If argv is not set (None or empty list), then
        sys.argv will be used as arguments for jami-commander.

    Example input argv: ["jami-commander"]
        ["jami-commander" "--version"]
        ["jami-commander" "--message" "Hello" --file "pic.jpg"]

    Returns int. 0 for success. Positive integer for failure.
        Returns the total number of errors encountered.

    Tries to avoid raising exceptions.

    """
    try:
        main_inner(argv)
    except (Exception, JamiCommanderError, JamiCommanderWarning) as e:
        if e not in (JamiCommanderError, JamiCommanderWarning):
            gs.err_count += 1
        tb = ""
        if gs.pa.debug > 0:
            tb = f"\nHere is the traceback.\n{traceback.format_exc()}"
        if e == JamiCommanderWarning:
            gs.log.warning(f"{e}{tb}")
        else:
            gs.log.error(f"{e}{tb}")
    if gs.err_count > 0 or gs.warn_count > 0:
        gs.log.info(
            f"{gs.err_count} "
            f"error{'' if gs.err_count == 1 else 's'} and "
            f"{gs.warn_count} "
            f"warning{'' if gs.warn_count == 1 else 's'} occurred."
        )
    return gs.err_count  # 0 for success


if __name__ == "__main__":
    sys.exit(main())

# EOF
