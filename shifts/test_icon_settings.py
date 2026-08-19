from django.test import SimpleTestCase



from biota_shifts.icon_settings import (

    get_icon_preset,

    load_icon_settings,

    save_icon_settings,

    set_icon_preset,

)

from biota_shifts.icons import get_icon, render_icon_html





class IconSettingsTests(SimpleTestCase):

    def setUp(self):
        save_icon_settings({}, preset="default")

    def tearDown(self):
        save_icon_settings({}, preset="default")



    def test_override_flaticon(self):

        save_icon_settings(

            {

                "action.upload": {"kind": "flaticon", "value": "fi fi-rr-cloud-upload"},

            }

        )

        spec = get_icon("action.upload")

        self.assertEqual(spec["value"], "fi fi-rr-cloud-upload")

        html = str(render_icon_html("action.upload", "ui-icon"))

        self.assertIn("fi-rr-cloud-upload", html)



    def test_reset_to_default(self):

        save_icon_settings(

            {

                "cabinet.notifications": {"kind": "emoji", "value": "📣"},

            }

        )

        save_icon_settings({})

        spec = get_icon("cabinet.notifications")

        self.assertEqual(spec["value"], "🔔")



    def test_load_empty(self):

        data = load_icon_settings()

        self.assertIn("overrides", data)

        self.assertEqual(data.get("preset"), "default")



    def test_override_hugeicons(self):

        save_icon_settings(

            {

                "action.upload": {"kind": "hugeicons", "value": "upload-01"},

            }

        )

        spec = get_icon("action.upload")

        self.assertEqual(spec["kind"], "hugeicons")

        self.assertEqual(spec["value"], "upload-01")

        html = str(render_icon_html("action.upload"))

        self.assertIn("<svg", html)

        self.assertIn("biota-icon--hgi", html)



    def test_preset_toggle_hugeicons(self):

        set_icon_preset("hugeicons")

        self.assertEqual(get_icon_preset(), "hugeicons")

        spec = get_icon("action.upload")

        self.assertEqual(spec["kind"], "hugeicons")

        self.assertEqual(spec["value"], "upload-01")



    def test_preset_toggle_default(self):

        set_icon_preset("hugeicons")

        set_icon_preset("default")

        self.assertEqual(get_icon_preset(), "default")

        spec = get_icon("action.upload")

        self.assertEqual(spec["kind"], "flaticon")

