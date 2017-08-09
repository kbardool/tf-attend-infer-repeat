import os
import shutil

import tensorflow as tf

from multi_mnist import read_and_decode
from air_model import AIRModel


RESULTS_FOLDER = "air_results/"
MODELS_FOLDER = RESULTS_FOLDER + "models/"
SUMMARIES_FOLDER = RESULTS_FOLDER + "summary/"
SOURCE_FOLDER = RESULTS_FOLDER + "source/"
DATA_FILE = "multi_mnist_data/common.tfrecords"

# removing results folder (with content) if exists
shutil.rmtree(RESULTS_FOLDER, ignore_errors=True)

# creating result directories
os.makedirs(RESULTS_FOLDER)
os.makedirs(MODELS_FOLDER)
os.makedirs(SUMMARIES_FOLDER)
os.makedirs(SOURCE_FOLDER)

# creating a copy of the current version of .py sources
for file in [f for f in os.listdir(".") if f.endswith(".py")]:
        shutil.copy(file, SOURCE_FOLDER + file)


EPOCHS = 300
BATCH_SIZE = 64
NUM_THREADS = 4
CANVAS_SIZE = 50

NUM_SUMMARIES_EACH_ITERATIONS = 10
IMG_SUMMARIES_EACH_ITERATIONS = 200
SAVE_MODEL_EACH_ITERATIONS = 10000
NUM_IMAGES_TO_SAVE = 24


# fetching a batch of numbers of
# digits and images from a queue
with tf.name_scope("pipeline"):
    filename_queue = tf.train.string_input_producer([DATA_FILE], num_epochs=EPOCHS)
    num_digits, images = read_and_decode(filename_queue, BATCH_SIZE, CANVAS_SIZE, NUM_THREADS)

# AIR model
model = AIRModel(
    images, num_digits,
    max_steps=3, max_digits=2, lstm_units=256, canvas_size=CANVAS_SIZE, windows_size=28,
    vae_latent_dimensions=50, vae_recognition_units=(512, 256), vae_generative_units=(256, 512),
    scale_prior_mean=-1.0, scale_prior_variance=0.1, shift_prior_mean=0.0, shift_prior_variance=1.0,
    vae_prior_mean=0.0, vae_prior_variance=1.0, vae_likelihood_std=0.3,
    z_pres_prior=1e-1, gumbel_temperature=10.0, learning_rate=1e-3,
    gradient_clipping_norm=10.0, num_summary_images=NUM_IMAGES_TO_SAVE,
    annealing_schedules={
        "z_pres_prior": {"init": 1e-1, "min": 1e-9, "factor": 0.5, "iters": 1000},
        "gumbel_temperature": {"init": 10.0, "min": 0.1, "factor": 0.8, "iters": 1000},
        "learning_rate": {"init": 1e-3, "min": 1e-4, "factor": 0.5, "iters": 1000}
    }
)


config = tf.ConfigProto()
config.gpu_options.allow_growth = True

with tf.Session(config=config) as sess:
    coord = tf.train.Coordinator()

    sess.run(tf.local_variables_initializer())
    sess.run(tf.global_variables_initializer())

    threads = tf.train.start_queue_runners(sess=sess, coord=coord)
    writer = tf.summary.FileWriter(SUMMARIES_FOLDER, sess.graph)
    saver = tf.train.Saver(max_to_keep=10000)

    num_summaries = tf.summary.merge_all("num.summaries")
    img_summaries = tf.summary.merge_all("img.summaries")

    try:
        while True:
            # training
            _, l, a, step = sess.run([
                model.training, model.loss,
                model.accuracy, model.global_step
            ])

            print("iteration {}\tloss {:.3f}\taccuracy {:.2f}".format(step, l, a))

            # saving summaries: numeric and image
            # it is assumed that image summary saving period
            # is divisible by numeric summary saving period
            if step % NUM_SUMMARIES_EACH_ITERATIONS == 0:
                if step % IMG_SUMMARIES_EACH_ITERATIONS == 0:
                    nums, imgs = sess.run([num_summaries, img_summaries])
                    writer.add_summary(imgs, step)
                else:
                    nums = sess.run(num_summaries)
                writer.add_summary(nums, step)

            # saving model checkpoints
            if step % SAVE_MODEL_EACH_ITERATIONS == 0:
                saver.save(
                    sess, MODELS_FOLDER + "air-model",
                    global_step=step
                )

    except tf.errors.OutOfRangeError:
        print()
        print("training has ended")
        print()

    finally:
        coord.request_stop()
        coord.join(threads)
