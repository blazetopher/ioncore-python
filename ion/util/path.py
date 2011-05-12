import os
from pkg_resources import resource_filename

def adjust_dir(filename):
    """
    @brief Compensates for different current directories in tests and production
    """
    if not filename:
        return None

    resolved_file = None

    if not '/' in filename: # Looking for a package
        resolved_file = filename
    else:
        # First try relative to the local directory
        relative_path = filename
        if os.getcwd().endswith("_temp"):
            relative_path = os.path.join('..', relative_path)
        if os.path.exists(relative_path):
            resolved_file = relative_path

        # Next try a file in the package (this does not need to know about the trial dir)
        if resolved_file is None:
            resolved_file = resource_filename('ion', os.path.join('..', filename))

        if not os.path.isabs(resolved_file):
            resolved_file = os.path.abspath(resolved_file)

    return resolved_file