import unittest
from backend.config import settings
from backend.db import init_db, rows
from backend.services import ServiceError, _extract_tts_audio
from backend.voices import DEFAULT_VOICE_ID, VOICE_IDS, VOICES

class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): init_db()
    def test_seeded_three_spots_and_qa(self):
        spots=rows('SELECT id,name FROM scenic_spots ORDER BY id')
        self.assertEqual([x['name'] for x in spots],['灵山景区','敦煌','西湖'])
        for spot in spots:
            count=rows('SELECT COUNT(*) count FROM qa_items WHERE scenic_spot_id=?',(spot['id'],))[0]['count']
            self.assertGreaterEqual(count,10)
    def test_tts_audio_parser(self):
        self.assertEqual(_extract_tts_audio({'code':3000,'data':'YWJjZGVm'}),b'abcdef')
    def test_tts_error(self):
        with self.assertRaises(ServiceError):_extract_tts_audio({'code':55000000,'message':'mismatch'})
    def test_voice_catalog(self):
        self.assertIn(DEFAULT_VOICE_ID,VOICE_IDS)
        self.assertGreaterEqual(len(VOICES),20)
    def test_persistence_directories(self):
        for folder in (settings.audio_dir,settings.video_dir,settings.material_dir):self.assertTrue(folder.is_dir())

if __name__=='__main__':unittest.main()
