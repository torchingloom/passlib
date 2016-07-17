#!/bin/sh
#
# helper script to build & upload passlib to pypi
#

SEP1="====================================================="
SEP2="-----------------------------------------------------"

#
# init config
#

if [ -z "$DRY_RUN" ]; then
    echo "DRY_RUN not set"
    exit 1
elif [ "$DRY_RUN" -eq 1 ]; then
    echo "dry run"
    UPLOAD_ARG=""
    UPLOAD_DOCS_ARG=""
else
    echo "real run"
    UPLOAD_ARG="upload"
    UPLOAD_DOCS_ARG="upload_docs"
fi

VSTR=`python setup.py --for-release --version`
VTAIL="Release-${VSTR}"

echo "$SEP1"
echo "DRY_RUN=$DRY_RUN"
echo "VERSION=$VSTR"

#
# upload to pypi
#
if [ -z "$SKIP_PYPI" ]; then

    # clean dir
    echo "\n$SEP1\ncleaning build dirs\n$SEP2"
    rm -rf build dist

    # upload source
    echo "\n$SEP1\nbuilding and uploading source to pypi\n$SEP2"
    python setup.py --for-release sdist bdist_wheel $UPLOAD_ARG

    # upload docs
    echo "\n$SEP1\nbuilding and uploading docs to pypi\n$SEP2"
    PASSLIB_DOCS="for-pypi" python setup.py --for-release build_sphinx $UPLOAD_DOCS_ARG

fi

echo "\n$SEP1\ndone."
