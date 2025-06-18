###################################################################################
#
#    Copyright (C) 2020 Cetmix OÜ
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU LESSER GENERAL PUBLIC LICENSE as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU LESSER GENERAL PUBLIC LICENSE for more details.
#
#    You should have received a copy of the GNU LESSER GENERAL PUBLIC LICENSE
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
###################################################################################

import base64
import string
from zlib import compress

maketrans = bytes.maketrans
plantuml_alphabet = (
    string.digits + string.ascii_uppercase + string.ascii_lowercase + "-_"
)
base64_alphabet = string.ascii_uppercase + string.ascii_lowercase + string.digits + "+/"
b64_to_plantuml = maketrans(
    base64_alphabet.encode("utf-8"), plantuml_alphabet.encode("utf-8")
)


def get_url(plantuml_text):
    zipped_str = compress(plantuml_text.encode("utf-8"))
    compressed_string = zipped_str[2:-4]
    return (
        base64.b64encode(compressed_string).translate(b64_to_plantuml).decode("utf-8")
    )
