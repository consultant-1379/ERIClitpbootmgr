#!/bin/sh

echo "Expand deps called"
cd target/deps
echo "cd to target deps dir"
for i in *rpm ; do rpm2cpio $i | cpio -idmv ; done

cd ../..
exit
