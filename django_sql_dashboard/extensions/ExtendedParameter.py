import re
from django.utils.html import escape
from django.utils.safestring import mark_safe

from ..utils import Parameter

class ExtendedParameter(Parameter):
    extract_re = re.compile(r"\%\(([\w\-]+)(?:\:([\w\-]+))?\)(s|(?:0?\.(\d+))?d|b)")
    extract_name_re = lambda name: re.compile(rf"\%\({name}(?:\:[\w\-]+)?\)(?:s|(?:0?\.(\d+))?d|b)")
    number_re = re.compile(r"^\d+(?:\.\d+)?")

    def __init__(self, name, default_value, typecode, decimals):
        if decimals:
            typecode = "d"
        self.typecode = typecode

        # Adapt default value depending on the type
        if default_value == "":
            if self.typecode == "b":
                default_value = "false"
            if self.typecode == "d":
                default_value = "0"

        self.decimals = int(decimals) if len(decimals) >= 1 else 0

        super().__init__(name, default_value)


    def ensure_consistency(self, previous):
        super().ensure_consistency(previous)
        if self.typecode != previous.typecode:
            raise ValueError("Invalid typecode specification '%s' for parameter '%s': previously registered with typecode '%s'" % (self.typecode, self.name, previous.typecode))
        if self.decimals != 0 and self.decimals != previous.typecode:
            raise ValueError("Invalid decimals specification '%d' for parameter '%s': previously registered with %d decimals" % (self.decimals, self.name, previous.decimals))

    def get_sanitized(self, value, for_default=False):
        value = super().get_sanitized(value, for_default=for_default)
        if value is None:
            return None
        
        if self.typecode == "s":
            # String parameter: no need to check sanity because we use psycopg2 parameter-passing feature
            return value

        # Need to check sanity
        if self.typecode == "b":
            value = value.lower()
            if not value in ["true", "false"]:
                raise ValueError("Invalid %svalue for bool parameter '%s': '%s'" % ("default " if for_default else "", self.name, value))
            return value
        elif self.typecode == "d":
            if not ExtendedParameter.number_re.match(value):
                raise ValueError("Invalid %svalue for number parameter '%s': '%s'" % ("default " if for_default else "", self.name, value))
            return value
        else:
            raise ValueError("Unsupported typecode '%s' for parameter '%s'" % (self.typecode, self.name))

    @property
    def step(self):
        """ Determine "step" attribute for number inputs """
        return pow(10, -1*self.decimals)

    def form_control(self):
        label = f"""<label for="qp_{escape(self.name)}">{escape(self.name)}</label>"""
        if self.typecode == 'd':
            control = f"""<input type="number" step="{str(self.step)}" id="qp_{escape(self.name)}" name="{escape(self.name)}" value="{escape(self.value) if self.value is not None else ""}">"""
        elif self.typecode == 'b':
            if self.default_value:
                control = f"""<input type="hidden" name="{escape(self.name)}" value="false">
                <input type="checkbox" id="qp_{escape(self.name)}" name="{escape(self.name)}" value="true" {"checked" if self.value == "true" else ""}>"""
            else:
                control = f"""<div>
                    <input type="radio" id="qp_{escape(self.name)}_null" name="{escape(self.name)}" value="" {"checked" if not self.value else ""}>
                    <label for="qp_{escape(self.name)}_null">null</label>

                    <input type="radio" id="qp_{escape(self.name)}_true" name="{escape(self.name)}" value="true" {"checked" if self.value == "true" else ""}>
                    <label for="qp_{escape(self.name)}_true">true</label>

                    <input type="radio" id="qp_{escape(self.name)}_false" name="{escape(self.name)}" value="false" {"checked" if self.value == "false" else ""}>
                    <label for="qp_{escape(self.name)}_false">false</label>
                </div>"""
        else:
            control = f"""<input type="text" id="qp_{escape(self.name)}" name="{escape(self.name)}" value="{escape(self.value) if self.value is not None else ""}">"""

        return mark_safe(label + '\n' + control)

    @classmethod
    def execute(cls, cursor, sql: str, parameters: list=[]):
        string_values = {}
        for parameter in parameters:
            if parameter.typecode == 's':
                # For strings, we will use psycopg2 name parameter passing
                string_values[parameter.name] = parameter.value
                # If a default value has been specified, this needs to be removed from the SQL
                if parameter.default_value != "":
                    sql = ExtendedParameter.extract_name_re(parameter.name).sub(f"%({parameter.name})s", sql)
            else:
                # For non-strings, we cannot use psycopg2 name parameter passing (not supported)
                value = parameter.value
                sql = ExtendedParameter.extract_name_re(parameter.name).sub(value if value is not None else "null", sql)

        cursor.execute(sql, string_values)
