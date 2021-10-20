[app]

# (str) Title of your application
title = Electrum

# (str) Package name
package.name = Electrum

# (str) Package domain (needed for android/ios packaging)
package.domain = org.electrum

# (str) Source code where the main.py live
source.dir = .

# (list) Source files to include (let empty to include all the files)
source.include_exts = py,png,jpg,kv,atlas,ttf,txt,gif,pem,mo,vs,fs,json,csv

# (list) Source files to exclude (let empty to not exclude anything)
source.exclude_exts = spec

# (list) List of directory to exclude (let empty to not exclude anything)
source.exclude_dirs = bin, build, dist, contrib,
    electrum/tests,
    electrum/gui/qt,
    electrum/gui/kivy/theming/light,
    packages/qdarkstyle,
    packages/qtpy
# (list) List of exclusions using pattern matching
source.exclude_patterns = Makefile,setup*

# (str) Application versioning (method 1)
version.regex = APK_VERSION = '(.*)'
version.filename = %(source.dir)s/electrum/version.py

# (str) Application versioning (method 2)
#version = 1.9.8

# (list) Application requirements
requirements =
    # note: re python3.8, see #6147
    hostpython3==3.7.9,
    python3==3.7.9,
    android,
    openssl,
    plyer,
    # kivy 1.11.1
    kivy==39c17457bae91baf8fe710dc989791e45879f136,
    libffi,
    libsecp256k1,
    cryptography

# (str) Presplash of the application
#presplash.filename = %(source.dir)s/gui/kivy/theming/splash.png
presplash.filename = %(source.dir)s/electrum/gui/icons/electrum_presplash.png

# (str) Icon of the application
icon.filename = %(source.dir)s/electrum/gui/icons/electrum_launcher.png

# (str) Supported orientation (one of landscape, portrait or all)
orientation = portrait

# (bool) Indicate if the application should be fullscreen or not
fullscreen = False


#
# Android specific
#

# (list) Permissions
android.permissions = INTERNET, CAMERA, WRITE_EXTERNAL_STORAGE

# (int) Android API to use  (targetSdkVersion AND compileSdkVersion)
# note: when changing, Dockerfile also needs to be changed to install corresponding build tools
android.api = 29

# (int) Minimum API required. You will need to set the android.ndk_api to be as low as this value.
android.minapi = 21

# (str) Android NDK version to use
android.ndk = 19c

# (int) Android NDK API to use (optional). This is the minimum API your app will support.
android.ndk_api = 21

# (bool) Use --private data storage (True) or --dir public storage (False)
android.private_storage = True

# (str) Android NDK directory (if empty, it will be automatically downloaded.)
android.ndk_path = /opt/android/android-ndk

# (str) Android SDK directory (if empty, it will be automatically downloaded.)
android.sdk_path = /opt/android/android-sdk

# (str) ANT directory (if empty, it will be automatically downloaded.)
android.ant_path = /opt/android/apache-ant

# (str) Android entry point, default is ok for Kivy-based app
#android.entrypoint = org.renpy.android.PythonActivity

# (list) List of Java .jar files to add to the libs so that pyjnius can access
# their classes. Don't add jars that you do not need, since extra jars can slow
# down the build process. Allows wildcards matching, for example:
# OUYA-ODK/libs/*.jar
#android.add_jars = foo.jar,bar.jar,path/to/more/*.jar
#android.add_jars = lib/android/zbar.jar

# (list) List of Java files to add to the android project (can be java or a
# directory containing the files)
android.add_src = electrum/gui/kivy/data/java-classes/

android.gradle_dependencies = me.dm7.barcodescanner:zxing:1.9.8

android.add_activities = org.electrum.qr.SimpleScannerActivity

# (str) python-for-android branch to use, if not master, useful to try
# not yet merged features.
#android.branch = master

# (str) OUYA Console category. Should be one of GAME or APP
# If you leave this blank, OUYA support will not be enabled
#android.ouya.category = GAME

# (str) Filename of OUYA Console icon. It must be a 732x412 png image.
#android.ouya.icon.filename = %(source.dir)s/data/ouya_icon.png

# (str) XML file to include as an intent filters in <activity> tag
android.manifest.intent_filters = contrib/android/bitcoin_intent.xml

# (str) launchMode to set for the main activity
android.manifest.launch_mode = singleTask

# (list) Android additionnal libraries to copy into libs/armeabi
#android.add_libs_armeabi = lib/android/*.so

# (bool) Indicate whether the screen should stay on
# Don't forget to add the WAKE_LOCK permission if you set this to True
#android.wakelock = False

# (str) The Android arch to build for, choices: armeabi-v7a, arm64-v8a, x86, x86_64
# note: can be overwritten by APP_ANDROID_ARCH env var
android.arch = armeabi-v7a

# (list) Android application meta-data to set (key=value format)
#android.meta_data =

# (list) Android library project to add (will be added in the
# project.properties automatically.)
#android.library_references =

android.whitelist = lib-dynload/_csv.so


#
# Python for android (p4a) specific
#

# (str) python-for-android git clone directory (if empty, it will be automatically cloned from github)
p4a.source_dir = /opt/python-for-android

# (str) The directory in which python-for-android should look for your own build recipes (if any)
#p4a.local_recipes =

# (str) Filename to the hook for p4a
#p4a.hook =

# (str) Bootstrap to use for android builds
# p4a.bootstrap = sdl2

# (int) port number to specify an explicit --port= p4a argument (eg for bootstrap flask)
#p4a.port =


#
# iOS specific
#

# (str) Name of the certificate to use for signing the debug version
# Get a list of available identities: buildozer ios list_identities
#ios.codesign.debug = "iPhone Developer: <lastname> <firstname> (<hexstring>)"

# (str) Name of the certificate to use for signing the release version
#ios.codesign.release = %(ios.codesign.debug)s



[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug (with command output))
log_level = 1


# -----------------------------------------------------------------------------
# List as sections
#
# You can define all the "list" as [section:key].
# Each line will be considered as a option to the list.
# Let's take [app] / source.exclude_patterns.
# Instead of doing:
#
#     [app]
#     source.exclude_patterns = license,data/audio/*.wav,data/images/original/*
#
# This can be translated into:
#
#     [app:source.exclude_patterns]
#     license
#     data/audio/*.wav
#     data/images/original/*
#

# -----------------------------------------------------------------------------
# Profiles
#
# You can extend section / key with a profile
# For example, you want to deploy a demo version of your application without
# HD content. You could first change the title to add "(demo)" in the name
# and extend the excluded directories to remove the HD content.
#
#     [app@demo]
#     title = My Application (demo)
#
#     [app:source.exclude_patterns@demo]
#     images/hd/*
#
# Then, invoke the command line with the "demo" profile:
#
#     buildozer --profile demo android debug
