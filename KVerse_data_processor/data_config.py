
chunking_config = {
    'chapter' : { 
        'chunk_size' : 1024,
        'chunk_overlap' : 256,
        'length_function' : len
    },
    'sub_chapter' : { 
        'chunk_size' : 512,
        'chunk_overlap' : 128,
        'length_function' : len
    }
}

sub_chapter_kwargs = {
    'Subject_Code' : 'subject_code',
    'Book_Index' : 'book_name',
    'Chapter_Index' : 'chapter_name',
    'Sub_Chapter_Index' : 'sub_chapter_name',
    'Page_Numbers' : 'page_numbers',
}

chapter_kwargs = {
    'Subject_Code' : 'subject_code',
    'Book_Index' : 'book_name',
    'Chapter_Index' : 'chapter_name',
    'Page_Numbers' : 'page_numbers'
}
