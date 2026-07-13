import unittest
from backend.config import settings
from backend.db import init_db, rows
from backend.services import ServiceError, _extract_tts_audio
from backend.voices import DEFAULT_VOICE_ID, VOICE_IDS, VOICES
from backend.pipeline import SOURCE_FILES, available_sources

class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): init_db()
    def test_seeded_three_spots_and_qa(self):
        spots=rows('SELECT id,name FROM scenic_spots ORDER BY id')
        self.assertEqual([x['name'] for x in spots],['灵山景区','敦煌','西湖'])
        for spot in spots:
            count=rows('SELECT COUNT(*) count FROM qa_items WHERE scenic_spot_id=?',(spot['id'],))[0]['count']
            self.assertGreaterEqual(count,30 if spot['name']=='灵山景区' else 10)
    def test_tts_audio_parser(self):
        self.assertEqual(_extract_tts_audio({'code':3000,'data':'YWJjZGVm'}),b'abcdef')
    def test_tts_error(self):
        with self.assertRaises(ServiceError):_extract_tts_audio({'code':55000000,'message':'mismatch'})
    def test_voice_catalog(self):
        self.assertIn(DEFAULT_VOICE_ID,VOICE_IDS)
        self.assertEqual(len(VOICES),20)
        self.assertEqual(VOICE_IDS, {
            'zh_female_tianmeixiaoyuan_uranus_bigtts','zh_female_vv_uranus_bigtts',
            'zh_female_gaolengyujie_uranus_bigtts','BV001_streaming','BV002_streaming',
            'BV113_streaming','BV033_streaming','BV102_streaming','BV503_streaming',
            'BV504_streaming','BV005_streaming','BV705_streaming','BV700_streaming',
            'BV034_streaming','BV701_streaming','BV007_streaming','BV051_streaming',
            'BV524_streaming','BV056_streaming','BV522_streaming'})
    def test_persistence_directories(self):
        for folder in (settings.audio_dir,settings.video_dir,settings.material_dir):self.assertTrue(folder.is_dir())
    def test_pipeline_schema_and_source_mapping(self):
        self.assertEqual(SOURCE_FILES['灵山景区'],'灵山.mp4')
        self.assertEqual(SOURCE_FILES['敦煌'],'敦煌.mp4')
        self.assertEqual(SOURCE_FILES['西湖'],'西湖.mp4')
        self.assertTrue(available_sources()['灵山景区']['available'])
        tables={x['name'] for x in rows("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({'pipeline_jobs','pipeline_items'} <= tables)

if __name__=='__main__':unittest.main()
