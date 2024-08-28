#!/usr/bin/python


def register():
    # this pure python trigger acts as if it were a legacy shell-trigger,
    # but is much faster. The return of this method indicates the trigger type
    return "/var/lib/cobbler/triggers/install/pre/*"


# signature is usually
#
# - run(api, args, logger)
#
def run(api, args, _):

    object_type = args[0]
    name = args[1]

    system = api.find_system(name)

    if object_type == "system" and system:
        system.set_comment("PXE_BOOTED")

    return 0
