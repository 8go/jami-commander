# jami-commander

Jami (https://jami.net) is a privacy-preserving peer-to-peer communication application available on many platforms. `Jami` is in concept similar to `Keet` (https://keet.io), both are peer-to-peer and use servers as little as possible. As a chat app it is similar to `Matrix` (https://http://matrix.org) as both can be self-hosted.

`jami-commander` (`jc` for short) is a simple but convenient CLI-based Jami client app for setting up accounts and swarms as well as sending.

`jami-commander` helps to set up a Jami account, configure the account and send messages and files to Jami peers. It provides the minimal set of commands to use `Jami` from the CLI.

The objective of `jami-commander` is to:

+ be able to use `Jami` from the terminal, the CLI, via SSH, and on head-less servers without monitor.
+ to use minimal resources. No Jami front-end (GUI) needs to be installed.
+ to be able to run it e.g. on a headless Raspberry Pi
+ to be able to perform minimal operations to run a bot, e.g. to publish daily weather information
+ be simple. It is written in Python.

Functionality is minimal. You are invited to help to improve `jami-commander`. Pull requests are welcome.

# Installation and Prerequisites

+ `jami-commander` is only a client. It requires the Jami `jamid` daemon to run to performs the work.
+ install `jami-commander`
  + `pip jami-commander`
  + see also https://pypi.org/pypi/jami-commander
+ install Jami daemon `jamid` as follows:
  + e.g. on Fedora 40, similar on Ubuntu 24.04, etc.
  + `sudo dnf-3 config-manager --add-repo https://dl.jami.net/stable/fedora_40/jami-stable.repo # add the Jami repo`
  + `sudo dnf install jami-daemon # install only the jamid daemon`
+ run the `jamid` daemon:
  + e.g. on Fedora 40, similar on Ubuntu 24.04, etc.
  + `/usr/libexec/jamid -p & # start the jamid daemon`
+ now you can start and run the `jami-commander`
  + try `jami-commander -h` first to see what is available

# Features

```
jami-commander supports these arguments:

--usage
  Print usage.
-h, --help
  Print help.
--manual
  Print manual.
--readme
  Print README.md file.
-d, --debug
  Print debug information.
--log-level DEBUG|INFO|WARNING|ERROR|CRITICAL [DEBUG|INFO|WARNING|ERROR|CRITICAL ...]
  Set the log level(s).
--verbose
  Set the verbosity level.
--add-account ALIAS HOSTNAME USERNAME PASSWORD
  Add a new Jami account.
--remove-account ACCOUNTID [ACCOUNTID ...]
  Remove a Jami account.
--get-conversations
  List all swarm conversations by ids.
--add-conversation
  Add a conversation to an account.
--remove-conversation
  Remove one or multiple conversations from an account.
--get-conversation-members
  List all members of one or multiple swarm conversations by ids.
--add-conversation-member USERID [USERID ...]
  Add member(s) to one or multiple swarm conversations.
--remove-conversation-member USERID [USERID ...]
  Remove member(s) from one or multiple swarm conversations.
-a ACCOUNTID, --account ACCOUNTID
  Connect to and use the specified account.
-c CONVERSATIONID [CONVERSATIONID ...], --conversations CONVERSATIONID [CONVERSATIONID ...]
  Specify one or multiple swarm conversations.
--get-enabled-accounts
  List all enabled accounts by ids.
-m TEXT [TEXT ...], --message TEXT [TEXT ...]
  Send one or multiple text messages.
-f FILE [FILE ...], --file FILE [FILE ...]
  Send one or multiple files (e.g. PDF, DOC, MP4).
-w, --html
  Send message as format "HTML".
-z, --markdown
  Send message as format "MARKDOWN".
-k, --code
  Send message as format "CODE".
-j, --emojize
  Send message after emojizing.
--split SEPARATOR
  Split message text into multiple Jami messages.
--separator SEPARATOR
  Set a custom separator used for certain print outs.
-o TEXT|JSON, --output TEXT|JSON
  Select an output format.
-v [PRINT|CHECK], -V [PRINT|CHECK], --version [PRINT|CHECK]
  Print version information or check for updates.
```
