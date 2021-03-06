import tensorflow as tf
import numpy as np
import math
import json
import random
from skimage.transform import resize

import RPN

import utils

def load_image_gt(dataset, config, image_id):
    image_id = int(image_id)
    image = dataset.load_image(image_id) #

    old_shape = 416
    image = resize(image,(config.IMAGE_MAX_DIM,config.IMAGE_MAX_DIM))

    shape = image.shape

    image = image * np.full((shape),255.0)

    window = (0,0,self.config.IMAGE_MAX_DIM,self.config.IMAGE_MAX_DIM)

    #print(window)
    #print(padding)


    bboxes = dataset.load_bboxes(image_id)
    class_ids = np.ones([bboxes.shape[0]], dtype=np.int32)

    for i,bbox in enumerate(bboxes):
        y1,x1,y2,x2 = bbox

        x1 = x1 * 1.0*config.IMAGE_MAX_DIM / old_shape
        x2 = x2 * 1.0*config.IMAGE_MAX_DIM / old_shape
        y1 = y1 * 1.0*config.IMAGE_MAX_DIM / old_shape
        y2 = y2 * 1.0*config.IMAGE_MAX_DIM / old_shape

        bboxes[i] = np.array([y1,x1,y2,x2])
    """
    if random.randint(0,1):
        import imgaug as ia
        import imgaug.augmenters as iaa

        bbs = []
        for bbox in bboxes:
            y1,x1,y2,x2 = bbox
            bbs.append(ia.BoundingBox(x1=x1,y1=y1,x2=x2,y2=y2))

            image_aug, bbs_aug = iaa.Fliplr(1.0)(image=image, bounding_boxes=bbs)

        image = image_aug

        gt_boxes_aug = np.zeros([len(bbs_aug),4], dtype=np.float32)

        for i,bbox in enumerate(bbs_aug):
            #print(bbox.y1,bbox.x1,bbox.y2,bbox.x2)
            y1,x1,y2,x2 = bbox.y1,bbox.x1,bbox.y2,bbox.x2

            gt_boxes_aug[i] = np.array([y1,x1,y2,x2])

        bboxes = gt_boxes_aug

    if random.randint(0,1):
        import imgaug as ia
        import imgaug.augmenters as iaa

        bbs = []
        for bbox in bboxes:
            y1,x1,y2,x2 = bbox
            bbs.append(ia.BoundingBox(x1=x1,y1=y1,x2=x2,y2=y2))

            image_aug, bbs_aug = iaa.Flipud(1.0)(image=image, bounding_boxes=bbs)

        image = image_aug

        gt_boxes_aug = np.zeros([len(bbs_aug),4], dtype=np.float32)

        for i,bbox in enumerate(bbs_aug):
            #print(bbox.y1,bbox.x1,bbox.y2,bbox.x2)
            y1,x1,y2,x2 = bbox.y1,bbox.x1,bbox.y2,bbox.x2

            gt_boxes_aug[i] = np.array([y1,x1,y2,x2])

        bboxes = gt_boxes_aug

    """
    #print(mask.shape)

    #for image meta

    active_class_ids = np.zeros([dataset.num_classes], dtype=np.int32)
    source_class_ids = dataset.source_class_ids[dataset.image_info[image_id]["source"]]
    active_class_ids[source_class_ids] = 1

    image_meta = utils.compose_image_meta(image_id, shape, window, active_class_ids)

    return image, image_meta, class_ids, bboxes

def gen(dataset, config, shuffle=True,batch_size=1):
    """
    shuffle: shuffle image every epoch
    return:
    - input_image
    - input_image_meta
    - input_rpn_match
    - input_rpn_bbox
    - input_gt_class_ids
    - input_gt_boxes
    """
    anchors = utils.generate_anchors(config.ANCHOR_SCALES,
                                     config.ANCHOR_RATIOS,
                                     config.ANCHOR_STRIDE,
                                     config.BACKBONE_SHAPES,
                                     config.BACKBONE_STRIDES)

    b = 0 #batch index
    image_ids = np.copy(dataset.image_ids)
    #print(image_ids)
    error_count = 0

    index=-1

    while True:
        try:
            index = (index+1) % len(image_ids)

            if shuffle and index==0:
                np.random.shuffle(image_ids)

            image_id = image_ids[index]

            input_image, input_image_meta, input_gt_class_ids, input_gt_boxes =\
                load_image_gt(dataset, config, image_id)

            #print(input_image_meta)
            #print(input_gt_class_ids)

            if not np.any(input_gt_class_ids > 0):
                continue

            #RPN targets
            rpn_match, rpn_bbox = RPN.build_targets(input_image.shape, anchors, input_gt_class_ids, input_gt_boxes, config)
            if b==0 :
                #initial
                batch_image = np.zeros((batch_size, ) + input_image.shape, dtype = np.float32)
                batch_image_meta = np.zeros((batch_size, ) + input_image_meta.shape, dtype = input_image_meta.dtype)
                batch_gt_class_ids = np.zeros((batch_size, config.MAX_GT_INSTANCES), dtype = np.int32)
                batch_gt_boxes = np.zeros((batch_size, config.MAX_GT_INSTANCES, 4), dtype = np.float32)
                batch_rpn_match = np.zeros([batch_size, anchors.shape[0], 1], dtype = rpn_match.dtype)
                batch_rpn_bbox = np.zeros([batch_size, config.RPN_TRAIN_ANCHORS_PER_IMAGE, 4], dtype = rpn_bbox.dtype)

            if input_gt_boxes.shape[0] > config.MAX_GT_INSTANCES:
                ids = np.random.choice(np.arange(input_gt_boxes.shape[0]),
                                       config.MAX_GT_INSTANCES, replace=False)
                input_gt_class_ids = input_gt_class_ids[ids]
                input_gt_boxes = input_gt_boxes[ids]

            batch_image[b] = utils.mold_image(input_image.astype(np.float32), config)
            batch_image_meta[b] = input_image_meta
            batch_gt_class_ids[b, :input_gt_class_ids.shape[0]] = input_gt_class_ids
            batch_gt_boxes[b, :input_gt_boxes.shape[0]] = input_gt_boxes
            batch_rpn_match[b] = rpn_match[:, np.newaxis]
            batch_rpn_bbox[b] = rpn_bbox

            b+=1

            if b>=batch_size:
                """
                inputs = [batch_image, batch_image_meta, batch_rpn_match, batch_gt_boxes,
                          batch_gt_class_ids,batch_gt_boxes, batch_gt_masks]
                outputs = []
                """
                inputs = [batch_image, batch_image_meta, batch_rpn_match, batch_rpn_bbox,
                          batch_gt_class_ids,batch_gt_boxes]
                outputs = []

                yield inputs, outputs

                b=0

        except (GeneratorExit, KeyboardInterrupt):
            raise
        except:
            # Log it and skip the image
            print("Error processing image: ", image_id)
            error_count += 1
            if error_count > 5:
                raise
