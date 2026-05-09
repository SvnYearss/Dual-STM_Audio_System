#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#pragma pack(push, 1)
typedef struct {
    char riff[4];
    uint32_t riff_size;
    char wave[4];
    char fmt_id[4];
    uint32_t fmt_size;
    uint16_t audio_format;
    uint16_t channels;
    uint32_t sample_rate;
    uint32_t byte_rate;
    uint16_t block_align;
    uint16_t bits_per_sample;
    uint16_t cb_size;
    uint16_t valid_bits_per_sample;
    uint32_t channel_mask;
    uint8_t subformat[16];
    char data_id[4];
    uint32_t data_size;
} WavExtensibleHeader;
#pragma pack(pop)

static uint16_t read_le16(const uint8_t bytes[2])
{
    return (uint16_t)bytes[0] | ((uint16_t)bytes[1] << 8);
}

static int16_t clamp_i16(double value)
{
    if (value > 32767.0) {
        return 32767;
    }
    if (value < -32768.0) {
        return -32768;
    }
    return (int16_t)value;
}

int main(int argc, char *argv[])
{
    uint32_t sample_rate = 44100;
    if (argc >= 2) {
        uint32_t requested_rate = (uint32_t)strtoul(argv[1], NULL, 10);
        if (requested_rate > 0U) {
            sample_rate = requested_rate;
        }
    }

    FILE *raw_file = fopen("recording.bin", "rb");
    if (raw_file == NULL) {
        printf("Error: Could not open recording.bin\n");
        return 1;
    }

    fseek(raw_file, 0, SEEK_END);
    uint32_t raw_size = (uint32_t)ftell(raw_file);
    fseek(raw_file, 0, SEEK_SET);

    uint32_t sample_count = raw_size / 2U;
    uint32_t data_size = sample_count * 2U;
    double dc_center = 2048.0;
    double gain = 16.0;

    if (sample_count > 0U) {
        uint64_t sample_sum = 0U;
        uint8_t raw_bytes[2];
        while (fread(raw_bytes, 1, 2, raw_file) == 2) {
            sample_sum += (uint64_t)(read_le16(raw_bytes) & 0x0FFFU);
        }
        dc_center = (double)sample_sum / (double)sample_count;

        fseek(raw_file, 0, SEEK_SET);
        double max_abs = 1.0;
        while (fread(raw_bytes, 1, 2, raw_file) == 2) {
            double centered = (double)(read_le16(raw_bytes) & 0x0FFFU) - dc_center;
            double abs_centered = centered < 0.0 ? -centered : centered;
            if (abs_centered > max_abs) {
                max_abs = abs_centered;
            }
        }

        gain = 28000.0 / max_abs;
        if (gain < 4.0) {
            gain = 4.0;
        } else if (gain > 64.0) {
            gain = 64.0;
        }
        fseek(raw_file, 0, SEEK_SET);
    }

    FILE *wav_file = fopen("output_audio.wav", "wb");
    if (wav_file == NULL) {
        printf("Error: Could not create output_audio.wav\n");
        fclose(raw_file);
        return 1;
    }

    static const uint8_t pcm_guid[16] = {
        0x01, 0x00, 0x00, 0x00,
        0x00, 0x00,
        0x10, 0x00,
        0x80, 0x00,
        0x00, 0xAA, 0x00, 0x38, 0x9B, 0x71
    };

    WavExtensibleHeader header;
    memcpy(header.riff, "RIFF", 4);
    header.riff_size = 4U + (8U + 40U) + (8U + data_size);
    memcpy(header.wave, "WAVE", 4);
    memcpy(header.fmt_id, "fmt ", 4);
    header.fmt_size = 40U;
    header.audio_format = 0xFFFE; /* WAVE_FORMAT_EXTENSIBLE */
    header.channels = 1U;
    header.sample_rate = sample_rate;
    header.bits_per_sample = 16U;       /* storage container */
    header.valid_bits_per_sample = 12U; /* actual ADC/audio resolution */
    header.block_align = 2U;
    header.byte_rate = sample_rate * header.block_align;
    header.cb_size = 22U;
    header.channel_mask = 0x00000004U;  /* front center mono */
    memcpy(header.subformat, pcm_guid, sizeof(pcm_guid));
    memcpy(header.data_id, "data", 4);
    header.data_size = data_size;

    fwrite(&header, sizeof(header), 1, wav_file);

    uint8_t raw_bytes[2];
    while (fread(raw_bytes, 1, 2, raw_file) == 2) {
        uint16_t raw_12bit = read_le16(raw_bytes) & 0x0FFFU;
        int16_t signed_16bit = clamp_i16(((double)raw_12bit - dc_center) * gain);
        fwrite(&signed_16bit, sizeof(signed_16bit), 1, wav_file);
    }

    fclose(raw_file);
    fclose(wav_file);

    printf("Converted %u 12-bit samples to output_audio.wav (%u Hz, 12 valid bits, center %.1f, gain %.1f)\n",
           sample_count, sample_rate, dc_center, gain);
    return 0;
}
