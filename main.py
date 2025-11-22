'''

existing databses with mood tags
MTG-Jamendo
    Entries: 55k
    Tags: Music genre, Instrument, Mood
    Non_Vocal?: no but 'filmscore' and 'cinema' exist
    VAD Score?: none
    Full Audio?: yes
    Tags List: datasets/jamendo_tags.json
    Access: https://github.com/MTG/mtg-jamendo-dataset
    Size (with audio): 508GB @ full quality, mood only 46GB (from
    Size (without):


Million Song Dataset (MSD)
	Entries: 1x10^6
    Tags: no so useful, see http://millionsongdataset.com/sites/default/files/AdditionalFiles/unique_mbtags.txt
    Moods: limited e.g. cinematic only
    Non_Vocal?: no found
    VAD Score?: none
    Full Audio?: no
    Access: http://millionsongdataset.com/pages/getting-dataset/
    Size (with audio): no audio included
    Size (without): 108GB full dataset, 300MB summary file with tags

Emomusic
    Entries: 744
    Tags: "angry pop track", "funny pop track"
    Moods: EmoTag  emotion scores ranging from 0 to 1 for 150 most popular Twitter emojis for 8 emotion classes
        (i.e. anger, anticipation, disgust, fear, joy, sadness, surprise, and trust).
    Non_Vocal?: unknown
    VAD Score?: YES
    Full Audio?: YES
    Access: request at https://cvml.unige.ch/databases/emoMusic/
    Size (with audio):
    Size (without):

    Mood/Emotion (Valence/Arousal)
    ~700 entries
    Valence (positive/negative) and Arousal (calm/exciting) scores

MagnaTagATune
	Entries:
    Tags:
    Moods:
    Non_Vocal?:
    VAD Score?:
    Full Audio?:
    Access:
    Size (with audio):
    Size (without):

    25,863 clips, user-generated tags (like "chill," "epic," "acoustic").

Another way?
    Match books to films -> find film scores and OST albums
    (slower) use spotify recommender to broaden playlists
    Save playlists to genre/mood types
    (tune) apply VAD score to tune to narrative pace?

'''