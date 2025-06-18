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

# Templates used to build UML structure

MODULE_PREFIX = (
    '!define Root(name,desc) class name as "desc" << (R,magenta) >>\n'
    '!define App(name,desc) class name as "desc" << (A,orange) >>\n'
    '!define Module(name,desc) class name as "desc" << (M,grey) >>\n'
    "!define tech_name(x) <b>x</b>\n"
    "!define installed(x) <color:green><i>x</i></color>\n"
    "!define not_installed(x) <color:red><i>x</i></color>\n"
    "!define free(x) <color:green><i>x</i></color>\n"
    "!define paid(x) <color:magenta><i>x - paid!</i></color>\n"
    "!define ee(x) <color:magenta><i>x</i></color>\n"
    "!define version(x) x\n"
    "!define author(x) x\n"
    "hide methods"
)

MODULE_TEMPLATE = (
    '{}({}, "{}") {{\n' "    {}\n" "    {}\n" "    version({}) {}\n" "    {}\n" "}}"
)

RELATION_TEMPLATE = "{} --> {}"
MAX_NAME_LEN = 20
MAX_NAME_WORDS = 4

MODEL_PREFIX = (
    '!define Model(name,desc) class name as "desc" << (M,#FFAAAA) >>\n'
    '!define TransientModel(name,desc) class name as "desc" << (T,magenta) >>\n'
    '!define AbstractModel(name,desc) class name as "desc" << (T,green) >>\n'
    "hide methods"
)

MODEL_TEMPLATE = '{}({}, "{}") {{\n' "{} \n" " }}"

PACKAGE_NEW = 'package "%s" {\n'
PACKAGE_INHERITED = 'package "%s" {\n'
