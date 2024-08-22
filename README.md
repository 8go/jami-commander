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
