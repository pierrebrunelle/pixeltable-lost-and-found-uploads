"""Neighborhood lost-and-found upload API built with Pixeltable.

Neighbors upload a photo (or a short video) of something they found. Pixeltable stores the file,
writes a thumbnail to the database's media destination (set per database in pixeltable.toml), captions the photo with a small vision
model, names its dominant color, and indexes it with CLIP. Someone who lost an item describes it
in words or uploads an old photo of it, and gets the closest found items back. One FastAPIRouter
serves the multipart uploads, the searches and the status updates.

Layout: UDFs live in udfs.py; this file holds table models, @pxt.query functions and routes.

    pxt schema update app.py lostfound
    python seed.py
    pxt service run app.py lostfound --port 8000
"""

from __future__ import annotations

import pixeltable as pxt
import pixeltable.functions as pxtf
from pixeltable.functions import openai
from pixeltable.serving import FastAPIRouter

from udfs import CAPTION_MODEL, CAPTION_PROMPT, CLIP_MODEL, color_hint, shortlist, vision_messages

TableModel = pxt.model_base()

CLIP = pxtf.huggingface.clip.using(model_id=CLIP_MODEL)


class Found(TableModel, name='found'):
    """One found item, reported with a photo."""

    item_id = pxt.Column(value=pxtf.uuid.uuid7(), primary_key=True)
    photo: pxt.Image
    spot: pxt.String
    found_on: pxt.String | None
    finder: pxt.String | None
    status: pxt.String | None  # open / claimed / returned

    thumb = photo.resize([320, 240])
    meta = photo.get_metadata()
    color = color_hint(thumb)
    vision = openai.chat_completions(
        vision_messages(CAPTION_PROMPT, thumb), model=CAPTION_MODEL, model_kwargs={'max_tokens': 60, 'temperature': 0}
    )
    caption = vision.choices[0].message.content.astype(pxt.String)

    __indexes__ = [pxt.EmbeddingIndex(photo, embedding=CLIP, name='photo_clip'), pxt.BtreeIndex(status)]


class Clips(TableModel, name='clips'):
    """A short video of a found item (e.g. a bike that is too big to carry home)."""

    clip_id = pxt.Column(value=pxtf.uuid.uuid7(), primary_key=True)
    video: pxt.Video
    spot: pxt.String
    finder: pxt.String | None

    duration = video.get_duration()
    poster = pxtf.video.extract_frame(video, timestamp=1.0)

    __indexes__ = [pxt.EmbeddingIndex(poster, embedding=CLIP, name='poster_clip')]


@pxt.query
def search_text(q: str, k: int = 3):
    """Found items whose photo best matches a text description (CLIP text-to-image)."""
    sim = Found.photo.similarity(string=q, idx='photo_clip')
    return (
        Found.where(Found.status != 'returned')
        .order_by(sim, asc=False)
        .limit(k)
        # item_id as text: a UUID inside a query result stored as a JSON column must be a string
        .select(item_id=pxtf.uuid.to_string(Found.item_id), spot=Found.spot, caption=Found.caption, color=Found.color, status=Found.status, score=sim)
    )


@pxt.query
def search_photo(photo: pxt.Image, k: int = 3):
    """Found items that look like an uploaded photo (CLIP image-to-image)."""
    sim = Found.photo.similarity(image=photo, idx='photo_clip')
    return Found.order_by(sim, asc=False).limit(k).select(Found.item_id, Found.spot, Found.caption, score=sim)


@pxt.query
def search_clips(q: str, k: int = 2):
    """Video reports whose poster frame matches a text description."""
    sim = Clips.poster.similarity(string=q, idx='poster_clip')
    return Clips.order_by(sim, asc=False).limit(k).select(Clips.clip_id, Clips.spot, Clips.duration, score=sim)


@pxt.query
def recent_found(n: int = 10):
    """The latest found items, newest first."""
    return Found.order_by(Found.item_id, asc=False).limit(n).select(
        Found.item_id, Found.spot, Found.found_on, Found.caption, Found.color, Found.status
    )


@pxt.query
def thumbnail(item_id: pxt.UUID):
    """The stored thumbnail of one found item (served as a file)."""
    return Found.where(Found.item_id == item_id).select(Found.thumb).limit(1)


class LostReports(TableModel, name='lost_reports'):
    """Someone describes what they lost; the closest found items are attached on insert."""

    report_id = pxt.Column(value=pxtf.uuid.uuid7(), primary_key=True)
    description: pxt.String
    lost_near: pxt.String | None
    contact: pxt.String | None

    hits = search_text(description)
    matches = shortlist(hits)


lostfound = FastAPIRouter(name='lostfound')

lostfound.add_insert_route(
    Found,
    path='/found',
    inputs=[Found.spot, Found.found_on, Found.finder, Found.status],
    uploadfile_inputs=[Found.photo],
    outputs=[Found.item_id, Found.caption, Found.color, Found.meta],
)
lostfound.add_insert_route(
    Found,
    path='/found/background',
    inputs=[Found.spot, Found.found_on, Found.finder, Found.status],
    uploadfile_inputs=[Found.photo],
    outputs=[Found.item_id, Found.caption, Found.color],
    background=True,
)
lostfound.add_insert_route(
    Clips,
    path='/found/clip',
    inputs=[Clips.spot, Clips.finder],
    uploadfile_inputs=[Clips.video],
    outputs=[Clips.clip_id, Clips.duration],
)
lostfound.add_update_route(Found, path='/found/status', inputs=[Found.status], outputs=[Found.item_id, Found.status])
lostfound.add_delete_route(Found, path='/found/delete')
lostfound.add_insert_route(
    LostReports,
    path='/lost',
    inputs=[LostReports.description, LostReports.lost_near, LostReports.contact],
    outputs=[LostReports.report_id, LostReports.matches],
)
lostfound.add_query_route(path='/search', query=search_text, method='get')
lostfound.add_query_route(path='/search/photo', query=search_photo, uploadfile_inputs=['photo'])
lostfound.add_query_route(path='/clips/search', query=search_clips, method='get')
lostfound.add_query_route(path='/found/recent', query=recent_found, method='get')
lostfound.add_query_route(path='/found/thumb', query=thumbnail, method='get', return_fileresponse=True)
