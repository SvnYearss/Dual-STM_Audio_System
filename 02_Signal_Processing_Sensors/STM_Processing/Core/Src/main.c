/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2026 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */
uint8_t rx_byte;
#define AUDIO_SAMPLE_MASK      0x0FFFU
#define OUTLIER_THRESHOLD_12B  600
#define MOVING_AVERAGE_WINDOW  3U
#define HCSR04_DEFAULT_TRIGGER_CM  10U
#define HCSR04_MIN_TRIGGER_CM      2U
#define HCSR04_MAX_TRIGGER_CM      200U
#define HCSR04_DEBOUNCE_COUNT  3U
/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
SPI_HandleTypeDef hspi1;
DMA_HandleTypeDef hdma_spi1_rx;

TIM_HandleTypeDef htim2;
TIM_HandleTypeDef htim7;
TIM_HandleTypeDef htim15;

UART_HandleTypeDef huart1;
UART_HandleTypeDef huart2;
DMA_HandleTypeDef hdma_usart2_tx;

/* USER CODE BEGIN PV */
uint8_t pc_rx_byte = 0;
uint8_t rx_buffer[2];
uint8_t sample_count = 0;

uint8_t system_state = '0';
uint8_t trigger_count = 0;
uint8_t release_count = 0;
uint32_t IC_Val1 = 0;
uint32_t IC_Val2 = 0;
uint32_t Difference = 0;
uint8_t Is_First_Captured = 0;
float distance = 0.0;
uint8_t distance_recording_active = 0;
uint8_t hcsr04_trigger_cm = HCSR04_DEFAULT_TRIGGER_CM;
uint8_t expecting_distance_threshold = 0;

uint16_t sample_history[MOVING_AVERAGE_WINDOW] = {0};
uint8_t buffer_index = 0;
uint16_t last_valid_sample = 0;
uint8_t downsample_counter = 0;
int THRESHOLD = 50;
uint16_t spi_rx_buffer[200];

/* ---- UART TX FIFO (4-slot circular queue) ---- */
#define TX_BUF_COUNT  4U
#define TX_BUF_SIZE   200U

static uint8_t tx_pool[TX_BUF_COUNT][TX_BUF_SIZE];
static volatile uint8_t tx_wr   = 0; /* next slot to fill  */
static volatile uint8_t tx_rd   = 0; /* next slot to send  */
static volatile uint8_t tx_cnt  = 0; /* slots waiting      */
static volatile uint8_t tx_busy = 0; /* DMA in progress    */
/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_DMA_Init(void);
static void MX_USART2_UART_Init(void);
static void MX_USART1_UART_Init(void);
static void MX_SPI1_Init(void);
static void MX_TIM2_Init(void);
static void MX_TIM7_Init(void);
static void MX_TIM15_Init(void);
/* USER CODE BEGIN PFP */
void delay_uS(uint16_t delay);
void HCSR04_Read(void);
static void SendPcStatus(const char *message);
static void ForwardSamplingCommand(uint8_t cmd);
static void UpdateDistanceTrigger(float distance_cm);
/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */
static uint16_t ProcessAudioSample(uint16_t sample)
{
    sample &= AUDIO_SAMPLE_MASK;

    if (sample_count == 0U)
    {
        for (uint8_t i = 0; i < MOVING_AVERAGE_WINDOW; i++)
        {
            sample_history[i] = sample;
        }
        last_valid_sample = sample;
        sample_count = 1U;
        return sample;
    }

    uint16_t accepted = sample;
    uint16_t mean = last_valid_sample;

    if (sample_count >= MOVING_AVERAGE_WINDOW)
    {
        uint32_t sum = 0U;
        for (uint8_t i = 0; i < MOVING_AVERAGE_WINDOW; i++)
        {
            sum += sample_history[i];
        }
        mean = (uint16_t)(sum / MOVING_AVERAGE_WINDOW);
        int diff = (int)sample - (int)mean;
        if (abs(diff) > OUTLIER_THRESHOLD_12B)
        {
            accepted = mean;
        }
    }
    else
    {
        sample_count++;
    }

    sample_history[buffer_index] = accepted;
    buffer_index++;
    if (buffer_index >= MOVING_AVERAGE_WINDOW)
    {
        buffer_index = 0U;
    }

    uint32_t filtered_sum = 0U;
    for (uint8_t i = 0; i < MOVING_AVERAGE_WINDOW; i++)
    {
        filtered_sum += sample_history[i];
    }
    last_valid_sample = (uint16_t)(filtered_sum / MOVING_AVERAGE_WINDOW) & AUDIO_SAMPLE_MASK;
    return last_valid_sample;
}

static void ForwardSamplingCommand(uint8_t cmd)
{
    HAL_UART_Transmit(&huart1, &cmd, 1, HAL_MAX_DELAY);
}

static void SendPcStatus(const char *message)
{
    HAL_UART_Transmit(&huart2, (uint8_t *)message, strlen(message), 20);
}

static void UpdateDistanceTrigger(float distance_cm)
{
    if (distance_cm > 0.0f && distance_cm <= (float)hcsr04_trigger_cm)
    {
        trigger_count++;
        release_count = 0;
        if ((trigger_count >= HCSR04_DEBOUNCE_COUNT) && (distance_recording_active == 0U))
        {
            uint8_t cmd = 'M';
            distance_recording_active = 1U;
            ForwardSamplingCommand(cmd);
        }
    }
    else if (distance_cm > (float)hcsr04_trigger_cm)
    {
        release_count++;
        trigger_count = 0;
        if ((release_count >= HCSR04_DEBOUNCE_COUNT) && (distance_recording_active != 0U))
        {
            uint8_t cmd = 'S';
            distance_recording_active = 0U;
            ForwardSamplingCommand(cmd);
        }
    }
}

/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{

  /* USER CODE BEGIN 1 */

  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/

  /* Reset of all peripherals, Initializes the Flash interface and the Systick. */
  HAL_Init();

  /* USER CODE BEGIN Init */

  /* USER CODE END Init */

  /* Configure the system clock */
  SystemClock_Config();

  /* USER CODE BEGIN SysInit */

  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_DMA_Init();
  MX_USART2_UART_Init();
  MX_USART1_UART_Init();
  MX_SPI1_Init();
  MX_TIM2_Init();
  MX_TIM7_Init();
  MX_TIM15_Init();
  /* USER CODE BEGIN 2 */
  HAL_TIM_Base_Start(&htim7);
  HAL_TIM_IC_Start_IT(&htim2, TIM_CHANNEL_1);
  HAL_UART_Receive_IT(&huart1, rx_buffer, 2);
  HAL_UART_Receive_IT(&huart2, &pc_rx_byte, 1);
  HAL_SPI_Receive_DMA(&hspi1, (uint8_t*)spi_rx_buffer, 200);
  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
  }
  /* USER CODE END 3 */
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  /** Configure the main internal regulator output voltage
  */
  if (HAL_PWREx_ControlVoltageScaling(PWR_REGULATOR_VOLTAGE_SCALE1) != HAL_OK)
  {
    Error_Handler();
  }

  /** Configure LSE Drive Capability
  */
  HAL_PWR_EnableBkUpAccess();
  __HAL_RCC_LSEDRIVE_CONFIG(RCC_LSEDRIVE_LOW);

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_LSE|RCC_OSCILLATORTYPE_MSI;
  RCC_OscInitStruct.LSEState = RCC_LSE_ON;
  RCC_OscInitStruct.MSIState = RCC_MSI_ON;
  RCC_OscInitStruct.MSICalibrationValue = 0;
  RCC_OscInitStruct.MSIClockRange = RCC_MSIRANGE_6;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_MSI;
  RCC_OscInitStruct.PLL.PLLM = 1;
  RCC_OscInitStruct.PLL.PLLN = 16;
  RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV7;
  RCC_OscInitStruct.PLL.PLLQ = RCC_PLLQ_DIV2;
  RCC_OscInitStruct.PLL.PLLR = RCC_PLLR_DIV2;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV1;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_1) != HAL_OK)
  {
    Error_Handler();
  }

  /** Enable MSI Auto calibration
  */
  HAL_RCCEx_EnableMSIPLLMode();
}

/**
  * @brief SPI1 Initialization Function
  * @param None
  * @retval None
  */
static void MX_SPI1_Init(void)
{

  /* USER CODE BEGIN SPI1_Init 0 */

  /* USER CODE END SPI1_Init 0 */

  /* USER CODE BEGIN SPI1_Init 1 */

  /* USER CODE END SPI1_Init 1 */
  /* SPI1 parameter configuration*/
  hspi1.Instance = SPI1;
  hspi1.Init.Mode = SPI_MODE_SLAVE;
  hspi1.Init.Direction = SPI_DIRECTION_2LINES_RXONLY;
  hspi1.Init.DataSize = SPI_DATASIZE_16BIT;
  hspi1.Init.CLKPolarity = SPI_POLARITY_LOW;
  hspi1.Init.CLKPhase = SPI_PHASE_1EDGE;
  hspi1.Init.NSS = SPI_NSS_SOFT;
  hspi1.Init.FirstBit = SPI_FIRSTBIT_MSB;
  hspi1.Init.TIMode = SPI_TIMODE_DISABLE;
  hspi1.Init.CRCCalculation = SPI_CRCCALCULATION_DISABLE;
  hspi1.Init.CRCPolynomial = 7;
  hspi1.Init.CRCLength = SPI_CRC_LENGTH_DATASIZE;
  hspi1.Init.NSSPMode = SPI_NSS_PULSE_DISABLE;
  if (HAL_SPI_Init(&hspi1) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN SPI1_Init 2 */

  /* USER CODE END SPI1_Init 2 */

}

/**
  * @brief TIM2 Initialization Function
  * @param None
  * @retval None
  */
static void MX_TIM2_Init(void)
{

  /* USER CODE BEGIN TIM2_Init 0 */

  /* USER CODE END TIM2_Init 0 */

  TIM_MasterConfigTypeDef sMasterConfig = {0};
  TIM_IC_InitTypeDef sConfigIC = {0};

  /* USER CODE BEGIN TIM2_Init 1 */

  /* USER CODE END TIM2_Init 1 */
  htim2.Instance = TIM2;
  htim2.Init.Prescaler = 32-1;
  htim2.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim2.Init.Period = 4294967295;
  htim2.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim2.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
  if (HAL_TIM_IC_Init(&htim2) != HAL_OK)
  {
    Error_Handler();
  }
  sMasterConfig.MasterOutputTrigger = TIM_TRGO_RESET;
  sMasterConfig.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  if (HAL_TIMEx_MasterConfigSynchronization(&htim2, &sMasterConfig) != HAL_OK)
  {
    Error_Handler();
  }
  sConfigIC.ICPolarity = TIM_INPUTCHANNELPOLARITY_RISING;
  sConfigIC.ICSelection = TIM_ICSELECTION_DIRECTTI;
  sConfigIC.ICPrescaler = TIM_ICPSC_DIV1;
  sConfigIC.ICFilter = 0;
  if (HAL_TIM_IC_ConfigChannel(&htim2, &sConfigIC, TIM_CHANNEL_1) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN TIM2_Init 2 */

  /* USER CODE END TIM2_Init 2 */

}

/**
  * @brief TIM7 Initialization Function
  * @param None
  * @retval None
  */
static void MX_TIM7_Init(void)
{

  /* USER CODE BEGIN TIM7_Init 0 */

  /* USER CODE END TIM7_Init 0 */

  TIM_MasterConfigTypeDef sMasterConfig = {0};

  /* USER CODE BEGIN TIM7_Init 1 */

  /* USER CODE END TIM7_Init 1 */
  htim7.Instance = TIM7;
  htim7.Init.Prescaler = 32-1;
  htim7.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim7.Init.Period = 65535;
  htim7.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
  if (HAL_TIM_Base_Init(&htim7) != HAL_OK)
  {
    Error_Handler();
  }
  sMasterConfig.MasterOutputTrigger = TIM_TRGO_RESET;
  sMasterConfig.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  if (HAL_TIMEx_MasterConfigSynchronization(&htim7, &sMasterConfig) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN TIM7_Init 2 */

  /* USER CODE END TIM7_Init 2 */

}

/**
  * @brief TIM15 Initialization Function
  * @param None
  * @retval None
  */
static void MX_TIM15_Init(void)
{

  /* USER CODE BEGIN TIM15_Init 0 */

  /* USER CODE END TIM15_Init 0 */

  TIM_ClockConfigTypeDef sClockSourceConfig = {0};
  TIM_MasterConfigTypeDef sMasterConfig = {0};

  /* USER CODE BEGIN TIM15_Init 1 */

  /* USER CODE END TIM15_Init 1 */
  htim15.Instance = TIM15;
  htim15.Init.Prescaler = 32000-1;
  htim15.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim15.Init.Period = 60-1;
  htim15.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim15.Init.RepetitionCounter = 0;
  htim15.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
  if (HAL_TIM_Base_Init(&htim15) != HAL_OK)
  {
    Error_Handler();
  }
  sClockSourceConfig.ClockSource = TIM_CLOCKSOURCE_INTERNAL;
  if (HAL_TIM_ConfigClockSource(&htim15, &sClockSourceConfig) != HAL_OK)
  {
    Error_Handler();
  }
  sMasterConfig.MasterOutputTrigger = TIM_TRGO_RESET;
  sMasterConfig.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  if (HAL_TIMEx_MasterConfigSynchronization(&htim15, &sMasterConfig) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN TIM15_Init 2 */

  /* USER CODE END TIM15_Init 2 */

}

/**
  * @brief USART1 Initialization Function
  * @param None
  * @retval None
  */
static void MX_USART1_UART_Init(void)
{

  /* USER CODE BEGIN USART1_Init 0 */

  /* USER CODE END USART1_Init 0 */

  /* USER CODE BEGIN USART1_Init 1 */

  /* USER CODE END USART1_Init 1 */
  huart1.Instance = USART1;
  huart1.Init.BaudRate = 115200;
  huart1.Init.WordLength = UART_WORDLENGTH_8B;
  huart1.Init.StopBits = UART_STOPBITS_1;
  huart1.Init.Parity = UART_PARITY_NONE;
  huart1.Init.Mode = UART_MODE_TX_RX;
  huart1.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart1.Init.OverSampling = UART_OVERSAMPLING_16;
  huart1.Init.OneBitSampling = UART_ONE_BIT_SAMPLE_DISABLE;
  huart1.AdvancedInit.AdvFeatureInit = UART_ADVFEATURE_NO_INIT;
  if (HAL_UART_Init(&huart1) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN USART1_Init 2 */

  /* USER CODE END USART1_Init 2 */

}

/**
  * @brief USART2 Initialization Function
  * @param None
  * @retval None
  */
static void MX_USART2_UART_Init(void)
{

  /* USER CODE BEGIN USART2_Init 0 */

  /* USER CODE END USART2_Init 0 */

  /* USER CODE BEGIN USART2_Init 1 */

  /* USER CODE END USART2_Init 1 */
  huart2.Instance = USART2;
  huart2.Init.BaudRate = 921600;
  huart2.Init.WordLength = UART_WORDLENGTH_8B;
  huart2.Init.StopBits = UART_STOPBITS_1;
  huart2.Init.Parity = UART_PARITY_NONE;
  huart2.Init.Mode = UART_MODE_TX_RX;
  huart2.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart2.Init.OverSampling = UART_OVERSAMPLING_16;
  huart2.Init.OneBitSampling = UART_ONE_BIT_SAMPLE_DISABLE;
  huart2.AdvancedInit.AdvFeatureInit = UART_ADVFEATURE_NO_INIT;
  if (HAL_UART_Init(&huart2) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN USART2_Init 2 */

  /* USER CODE END USART2_Init 2 */

}

/**
  * Enable DMA controller clock
  */
static void MX_DMA_Init(void)
{

  /* DMA controller clock enable */
  __HAL_RCC_DMA1_CLK_ENABLE();

  /* DMA interrupt init */
  /* DMA1_Channel2_IRQn interrupt configuration */
  HAL_NVIC_SetPriority(DMA1_Channel2_IRQn, 0, 0);
  HAL_NVIC_EnableIRQ(DMA1_Channel2_IRQn);
  /* DMA1_Channel7_IRQn interrupt configuration */
  HAL_NVIC_SetPriority(DMA1_Channel7_IRQn, 0, 0);
  HAL_NVIC_EnableIRQ(DMA1_Channel7_IRQn);

}

/**
  * @brief GPIO Initialization Function
  * @param None
  * @retval None
  */
static void MX_GPIO_Init(void)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};
  /* USER CODE BEGIN MX_GPIO_Init_1 */

  /* USER CODE END MX_GPIO_Init_1 */

  /* GPIO Ports Clock Enable */
  __HAL_RCC_GPIOC_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();

  /*Configure GPIO pin Output Level */
  HAL_GPIO_WritePin(GPIOA, GPIO_PIN_4, GPIO_PIN_RESET);

  /*Configure GPIO pin : PA4 */
  GPIO_InitStruct.Pin = GPIO_PIN_4;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

  /* USER CODE BEGIN MX_GPIO_Init_2 */

  /* USER CODE END MX_GPIO_Init_2 */
}

/* USER CODE BEGIN 4 */
void HAL_TIM_PeriodElapsedCallback (TIM_HandleTypeDef* htim)
{
  if (htim == &htim15)
  {
      if (system_state == 'D')
      {
          HCSR04_Read();
      }
  }
}

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
	if(huart->Instance == USART2)
	{
		if (expecting_distance_threshold != 0U)
		{
			if (pc_rx_byte < HCSR04_MIN_TRIGGER_CM)
			{
				hcsr04_trigger_cm = HCSR04_MIN_TRIGGER_CM;
			}
			else if (pc_rx_byte > HCSR04_MAX_TRIGGER_CM)
			{
				hcsr04_trigger_cm = HCSR04_MAX_TRIGGER_CM;
			}
			else
			{
				hcsr04_trigger_cm = pc_rx_byte;
			}

			trigger_count = 0;
			release_count = 0;
			expecting_distance_threshold = 0U;

			char status_msg[16];
			snprintf(status_msg, sizeof(status_msg), "ACK:R:%u\n", hcsr04_trigger_cm);
			SendPcStatus(status_msg);
		}
		else if(pc_rx_byte == 'M' || pc_rx_byte == 'S')
		{
			system_state = pc_rx_byte;
			HAL_TIM_Base_Stop_IT(&htim15);
			trigger_count = 0;
			release_count = 0;
			distance_recording_active = (pc_rx_byte == 'M') ? 1U : 0U;
			SendPcStatus((pc_rx_byte == 'M') ? "ACK:M\n" : "ACK:S\n");
			ForwardSamplingCommand(pc_rx_byte);
		}
		else if (pc_rx_byte == 'D')
		{
			system_state = 'D';
			trigger_count = 0;
			release_count = 0;
			distance_recording_active = 0U;
			uint8_t stop_cmd = 'S';
			SendPcStatus("ACK:D\n");
			ForwardSamplingCommand(stop_cmd);
			HAL_TIM_Base_Start_IT(&htim15);
		}
		else if (pc_rx_byte == 'R')
		{
			expecting_distance_threshold = 1U;
		}

		HAL_UART_Receive_IT(&huart2, &pc_rx_byte, 1);
	}
}

void HAL_TIM_IC_CaptureCallback(TIM_HandleTypeDef *htim)
{
	if (htim->Instance == TIM2 && htim->Channel == HAL_TIM_ACTIVE_CHANNEL_1)
	{
		if (Is_First_Captured == 0)
		{
			IC_Val1 = HAL_TIM_ReadCapturedValue(htim, TIM_CHANNEL_1);
			Is_First_Captured = 1;
			__HAL_TIM_SET_CAPTUREPOLARITY(htim, TIM_CHANNEL_1, TIM_INPUTCHANNELPOLARITY_FALLING);
		}
		else if (Is_First_Captured == 1)
		{
			IC_Val2 = HAL_TIM_ReadCapturedValue(htim, TIM_CHANNEL_1);

			if (IC_Val2 >= IC_Val1) {
				Difference = IC_Val2 - IC_Val1;
			} else {
				Difference = (0xFFFFFFFFU - IC_Val1) + IC_Val2 + 1U;
			}

			distance = Difference * 0.0343 / 2.0;
			Is_First_Captured = 0;
			__HAL_TIM_SET_CAPTUREPOLARITY(htim, TIM_CHANNEL_1, TIM_INPUTCHANNELPOLARITY_RISING);

			if (system_state == 'D')
			{
				UpdateDistanceTrigger(distance);
			}
		}
	}
}

void delay_uS(uint16_t delay)
{
	__HAL_TIM_SET_COUNTER(&htim7, 0);
	while(__HAL_TIM_GET_COUNTER(&htim7) < delay) {}
}

void HCSR04_Read(void)
{
    Is_First_Captured = 0;
    __HAL_TIM_SET_CAPTUREPOLARITY(&htim2, TIM_CHANNEL_1, TIM_INPUTCHANNELPOLARITY_RISING);
    HAL_GPIO_WritePin(GPIOA, GPIO_PIN_4, GPIO_PIN_SET);
    delay_uS(10);
    HAL_GPIO_WritePin(GPIOA, GPIO_PIN_4, GPIO_PIN_RESET);
}

static uint8_t tx_queue_full(void)
{
    uint8_t usable_slots = TX_BUF_COUNT - ((tx_busy != 0U) ? 1U : 0U);
    return (tx_cnt >= usable_slots) ? 1U : 0U;
}

/* Enqueue a filled TX buffer and kick DMA if idle */
static void tx_enqueue(void)
{
    uint8_t next_wr = (tx_wr + 1U) % TX_BUF_COUNT;
    if (tx_queue_full()) {
        return;
    }
    tx_wr = next_wr;
    tx_cnt++;

    if (!tx_busy) {
        tx_busy = 1U;
        HAL_UART_Transmit_DMA(&huart2, tx_pool[tx_rd], TX_BUF_SIZE);
        tx_rd = (tx_rd + 1U) % TX_BUF_COUNT;
        tx_cnt--;
    }
}

/* UART TX complete – send next queued buffer if any */
void HAL_UART_TxCpltCallback(UART_HandleTypeDef *huart)
{
    if (huart->Instance == USART2) {
        if (tx_cnt > 0U) {
            HAL_UART_Transmit_DMA(&huart2, tx_pool[tx_rd], TX_BUF_SIZE);
            tx_rd = (tx_rd + 1U) % TX_BUF_COUNT;
            tx_cnt--;
        } else {
            tx_busy = 0U;
        }
    }
}

void HAL_SPI_RxHalfCpltCallback(SPI_HandleTypeDef *hspi)
{
    if(hspi->Instance == SPI1)
    {
        if (tx_queue_full()) {
            return;
        }
        uint8_t *buf = tx_pool[tx_wr];
        for(int i = 0; i < 100; i++)
        {
            uint16_t avg = ProcessAudioSample(spi_rx_buffer[i]);
            buf[i * 2]     = (uint8_t)(avg & 0xFF);
            buf[i * 2 + 1] = (uint8_t)((avg >> 8) & 0x0F);
        }
        tx_enqueue();
    }
}

void HAL_SPI_RxCpltCallback(SPI_HandleTypeDef *hspi)
{
    if(hspi->Instance == SPI1)
    {
        if (tx_queue_full()) {
            return;
        }
        uint8_t *buf = tx_pool[tx_wr];
        for(int i = 0; i < 100; i++)
        {
            uint16_t avg = ProcessAudioSample(spi_rx_buffer[i + 100]);
            buf[i * 2]     = (uint8_t)(avg & 0xFF);
            buf[i * 2 + 1] = (uint8_t)((avg >> 8) & 0x0F);
        }
        tx_enqueue();
    }
}
/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  /* User can add his own implementation to report the HAL error return state */
  __disable_irq();
  while (1)
  {
  }
  /* USER CODE END Error_Handler_Debug */
}

#ifdef  USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
