from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser


@dataclass
class Control:
    tag: str
    name: str
    value: str = ""
    control_type: str = ""
    attrs: dict[str, str] = field(default_factory=dict)


@dataclass
class Form:
    name: str = ""
    form_id: str = ""
    action: str = ""
    method: str = "get"
    controls: list[Control] = field(default_factory=list)

    @property
    def fields(self) -> dict[str, str]:
        fields: dict[str, str] = {}
        for control in self.controls:
            if control.name:
                if control.control_type in {"checkbox", "radio"} and "checked" not in control.attrs:
                    continue
                fields[control.name] = control.value
        return fields


class FormParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.forms: list[Form] = []
        self._current: Form | None = None
        self._select_name = ""
        self._select_has_value = False
        self._textarea_name = ""
        self._textarea_value: list[str] = []

    def handle_starttag(self, tag: str, attrs_raw):
        attrs = {key.lower(): (value or "") for key, value in attrs_raw}
        tag = tag.lower()

        if tag == "form":
            self._current = Form(
                name=attrs.get("name", ""),
                form_id=attrs.get("id", ""),
                action=attrs.get("action", ""),
                method=(attrs.get("method", "get") or "get").lower(),
            )
            self.forms.append(self._current)
            return

        if self._current is None:
            return

        if tag == "input":
            control_type = attrs.get("type", "text").lower()
            name = attrs.get("name", attrs.get("id", ""))
            if name and control_type not in {"button", "submit", "reset", "image"}:
                self._current.controls.append(
                    Control(
                        tag=tag,
                        name=name,
                        value=attrs.get("value", ""),
                        control_type=control_type,
                        attrs=attrs,
                    )
                )
            return

        if tag == "select":
            self._select_name = attrs.get("name", attrs.get("id", ""))
            self._select_has_value = False
            if self._select_name:
                self._current.controls.append(
                    Control(tag=tag, name=self._select_name, value="", attrs=attrs)
                )
            return

        if tag == "option" and self._select_name:
            selected = "selected" in attrs
            if selected or not self._select_has_value:
                self._replace_value(self._select_name, attrs.get("value", ""))
                self._select_has_value = True
            return

        if tag == "textarea":
            self._textarea_name = attrs.get("name", attrs.get("id", ""))
            self._textarea_value = []

    def handle_data(self, data: str):
        if self._textarea_name:
            self._textarea_value.append(data)

    def handle_endtag(self, tag: str):
        tag = tag.lower()
        if tag == "form":
            self._current = None
        elif tag == "select":
            self._select_name = ""
            self._select_has_value = False
        elif tag == "textarea" and self._current is not None:
            if self._textarea_name:
                self._current.controls.append(
                    Control(
                        tag="textarea",
                        name=self._textarea_name,
                        value="".join(self._textarea_value),
                    )
                )
            self._textarea_name = ""
            self._textarea_value = []

    def _replace_value(self, name: str, value: str) -> None:
        if self._current is None:
            return
        for control in reversed(self._current.controls):
            if control.name == name:
                control.value = value
                return


def parse_forms(html: str) -> list[Form]:
    parser = FormParser()
    parser.feed(html)
    return parser.forms
