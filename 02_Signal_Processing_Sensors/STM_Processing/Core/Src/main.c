/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Processing STM32 - Signal processing, sensor, command routing
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */

/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */
#define AUDIO_INPUT_RATE_HZ        44077U
#define AUDIO_OUTPUT_RATE_HZ       (AUDIO_INPUT_RATE_HZ / 2U)
#define SPI_LINK_CMD_START         ((uint16_t)'M')
#define SPI_LINK_CMD_STOP          ((uint16_t)'S')
#define SPI_LINK_SAMPLE_MASK       0x03FFU
#define AUDIO_FILTER_LEN           5U
#define OUTLIER_THRESHOLD_10BIT    160U
#define OUTLIER_RECOVERY_COUNT     4U

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
SPI_HandleTypeDef hspi1;

TIM_HandleTypeDef htim2;
TIM_HandleTypeDef htim15;

UART_HandleTypeDef huart1;
UART_HandleTypeDef huart2;

/* USER CODE BEGIN PV */
uint8_t pc_rx_byte;       // Byte received from PC (USART2)

// HC-SR04 sensor
volatile uint32_t IC_Val1 = 0;
volatile uint32_t IC_Val2 = 0;
volatile uint32_t Difference = 0;
volatile uint8_t Is_First_Captured = 0;
volatile uint32_t distance_um = 0;
volatile uint8_t distance_ready = 0;

// System state: 'S'=stop, 'M'=manual, 'D'=distance wait, 'R'=recording, 'T'=test
volatile uint8_t system_state = 'S';

// Distance trigger config
uint32_t distance_threshold_um = 100000;  // Default 10cm = 100000um (configurable)
#define DEBOUNCE_COUNT 3  // Require 3 consecutive readings to trigger/stop
uint8_t trigger_count = 0;  // Consecutive in-range readings
uint8_t release_count = 0;  // Consecutive out-of-range readings
volatile uint8_t pc_pending_threshold_byte = 0;

volatile uint16_t spi_tx_command = SPI_LINK_CMD_STOP;
volatile uint32_t spi_rx_sample_count = 0;
volatile uint32_t spi_overrun_count = 0;
volatile uint32_t pc_uart_drop_count = 0;

static uint16_t ma_buffer[AUDIO_FILTER_LEN] = {0};
static uint32_t ma_sum = 0;
static uint8_t ma_index = 0;
static uint8_t ma_count = 0;
static uint8_t downsample_phase = 0;
static uint8_t outlier_run_count = 0;
static uint16_t last_outlier_sample = 0;
/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_USART1_UART_Init(void);
static void MX_TIM15_Init(void);
static void MX_TIM2_Init(void);
static void MX_SPI1_Init(void);
static void MX_USART2_UART_Init(void);
/* USER CODE BEGIN PFP */
void HCSR04_Read(void);
static void SPI1_Link_Slave_Init(void);
static void SPI1_Link_SetCommand(uint16_t command);
static void AudioFilter_Reset(void);
static void AudioFilter_Prime(uint16_t sample_10bit);
static void AudioFilter_ProcessSample(uint16_t sample_10bit);
static void PC_UART_SendAudioByte(uint8_t sample_8bit);
/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */

// Send a string via UART, one byte at a time
static void uart_send_str(UART_HandleTypeDef *huart, const char *str)
{
	while (*str) {
		HAL_UART_Transmit(huart, (uint8_t*)str, 1, 10);
		str++;
	}
}

// Manual uint32 to decimal string (no printf dependency)
static char* u32_to_str(uint32_t val, char *buf, int buflen)
{
	buf[buflen - 1] = '\0';
	int pos = buflen - 2;
	if (val == 0) {
		buf[pos] = '0';
		return &buf[pos];
	}
	while (val > 0 && pos >= 0) {
		buf[pos--] = '0' + (val % 10);
		val /= 10;
	}
	return &buf[pos + 1];
}

void HCSR04_Read(void)
{
	HAL_GPIO_WritePin(HCSR04_TRIG_GPIO_Port, HCSR04_TRIG_Pin, GPIO_PIN_SET);
	for (volatile int i = 0; i < 300; i++) {}  // ~10us delay at 32MHz
	HAL_GPIO_WritePin(HCSR04_TRIG_GPIO_Port, HCSR04_TRIG_Pin, GPIO_PIN_RESET);
}

static void SPI1_Link_Slave_Init(void)
{
	GPIO_InitTypeDef GPIO_InitStruct = {0};

	__HAL_RCC_GPIOB_CLK_ENABLE();
	__HAL_RCC_SPI1_CLK_ENABLE();

	/*
	 * Inter-board SPI link:
	 * PB3 = SPI1_SCK, PB4 = SPI1_MISO, PB5 = SPI1_MOSI, AF5.
	 * This board is the slave; the Sampling STM clocks one 16-bit word per
	 * 44 kHz sample and reads the command word returned on MISO.
	 */
	GPIO_InitStruct.Pin = GPIO_PIN_3 | GPIO_PIN_4 | GPIO_PIN_5;
	GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;
	GPIO_InitStruct.Pull = GPIO_NOPULL;
	GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_VERY_HIGH;
	GPIO_InitStruct.Alternate = GPIO_AF5_SPI1;
	HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);

	SPI1->CR1 = 0U;
	SPI1->CR2 = 0U;
	SPI1->CR1 = SPI_CR1_SSM;
	SPI1->CR2 = (15U << SPI_CR2_DS_Pos) | SPI_CR2_RXNEIE | SPI_CR2_ERRIE;
	SPI1->CR1 |= SPI_CR1_SPE;
	*((__IO uint16_t *)&SPI1->DR) = spi_tx_command;

	HAL_NVIC_SetPriority(SPI1_IRQn, 0, 0);
	HAL_NVIC_EnableIRQ(SPI1_IRQn);
}

static void SPI1_Link_SetCommand(uint16_t command)
{
	spi_tx_command = command;
	if ((SPI1->SR & SPI_SR_TXE) != 0U)
	{
		*((__IO uint16_t *)&SPI1->DR) = spi_tx_command;
	}
}

static void AudioFilter_Reset(void)
{
	uint32_t primask = __get_PRIMASK();
	__disable_irq();

	for (uint8_t i = 0; i < AUDIO_FILTER_LEN; i++)
	{
		ma_buffer[i] = 0;
	}
	ma_sum = 0;
	ma_index = 0;
	ma_count = 0;
	downsample_phase = 0;
	outlier_run_count = 0;
	last_outlier_sample = 0;

	if (primask == 0U)
	{
		__enable_irq();
	}
}

static void AudioFilter_Prime(uint16_t sample_10bit)
{
	ma_sum = 0;
	for (uint8_t i = 0; i < AUDIO_FILTER_LEN; i++)
	{
		ma_buffer[i] = sample_10bit;
		ma_sum += sample_10bit;
	}
	ma_index = 0;
	ma_count = AUDIO_FILTER_LEN;
	outlier_run_count = 0;
	last_outlier_sample = sample_10bit;
}

static void PC_UART_SendAudioByte(uint8_t sample_8bit)
{
	if ((USART2->ISR & USART_ISR_TXE) != 0U)
	{
		USART2->TDR = sample_8bit;
	}
	else
	{
		pc_uart_drop_count++;
	}
}

static void AudioFilter_ProcessSample(uint16_t sample_10bit)
{
	sample_10bit &= SPI_LINK_SAMPLE_MASK;

	uint16_t mean = (ma_count > 0U) ? (uint16_t)(ma_sum / ma_count) : sample_10bit;
	uint16_t diff = (sample_10bit > mean) ? (sample_10bit - mean) : (mean - sample_10bit);
	uint16_t accepted_sample = sample_10bit;

	if ((ma_count >= AUDIO_FILTER_LEN) && (diff > OUTLIER_THRESHOLD_10BIT))
	{
		uint16_t outlier_step = (sample_10bit > last_outlier_sample)
			? (sample_10bit - last_outlier_sample)
			: (last_outlier_sample - sample_10bit);

		// Several similar outliers in a row are a real level change, not a spike.
		if ((outlier_run_count > 0U) && (outlier_step <= OUTLIER_THRESHOLD_10BIT))
		{
			outlier_run_count++;
		}
		else
		{
			outlier_run_count = 1;
		}
		last_outlier_sample = sample_10bit;

		if (outlier_run_count >= OUTLIER_RECOVERY_COUNT)
		{
			AudioFilter_Prime(sample_10bit);
			accepted_sample = sample_10bit;
		}
		else
		{
			accepted_sample = mean;
		}
	}
	else
	{
		outlier_run_count = 0;
		last_outlier_sample = sample_10bit;
	}

	if (ma_count < AUDIO_FILTER_LEN)
	{
		ma_buffer[ma_index] = accepted_sample;
		ma_sum += accepted_sample;
		ma_count++;
	}
	else
	{
		ma_sum -= ma_buffer[ma_index];
		ma_buffer[ma_index] = accepted_sample;
		ma_sum += accepted_sample;
	}

	ma_index = (uint8_t)((ma_index + 1U) % AUDIO_FILTER_LEN);

	downsample_phase ^= 1U;
	if (downsample_phase == 0U)
	{
		uint16_t filtered = (uint16_t)(ma_sum / ma_count);
		PC_UART_SendAudioByte((uint8_t)(filtered >> 2));
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
  MX_USART1_UART_Init();
  MX_TIM15_Init();
  MX_TIM2_Init();
  MX_SPI1_Init();
  MX_USART2_UART_Init();
  /* USER CODE BEGIN 2 */

  // Configure HC-SR04 trigger on PA4; echo is PA5/TIM2_CH1.
  {
	  GPIO_InitTypeDef GPIO_InitStruct = {0};
	  __HAL_RCC_GPIOA_CLK_ENABLE();
	  GPIO_InitStruct.Pin = HCSR04_TRIG_Pin;
	  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
	  GPIO_InitStruct.Pull = GPIO_NOPULL;
	  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
	  HAL_GPIO_Init(HCSR04_TRIG_GPIO_Port, &GPIO_InitStruct);
	  HAL_GPIO_WritePin(HCSR04_TRIG_GPIO_Port, HCSR04_TRIG_Pin, GPIO_PIN_RESET);
  }

  // Init timers for HC-SR04
  HAL_TIM_IC_Start_IT(&htim2, TIM_CHANNEL_1);
  SPI1_Link_Slave_Init();

  // Start UART receive from the PC. Inter-board audio now uses SPI1.
  HAL_UART_Receive_IT(&huart2, &pc_rx_byte, 1);
  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */

	  // === Distance reporting (Test Mode) ===
	  if (system_state == 'T' && distance_ready)
	  {
		  distance_ready = 0;
		  uint32_t d = distance_um;
		  uint32_t cm_whole = d / 10000;
		  uint32_t cm_frac  = (d % 10000) / 100;
		  char tmp[12];

		  // Send distance directly to PC via USART2 (bypasses moving average)
		  uart_send_str(&huart2, "DIST:");
		  uart_send_str(&huart2, u32_to_str(cm_whole, tmp, sizeof(tmp)));
		  uart_send_str(&huart2, ".");
		  if (cm_frac < 10) uart_send_str(&huart2, "0");
		  uart_send_str(&huart2, u32_to_str(cm_frac, tmp, sizeof(tmp)));
		  uart_send_str(&huart2, "\r\n");
	  }

	  // === Distance Trigger Mode: auto start/stop with debounce ===
	  if (system_state == 'D' && distance_ready)
	  {
		  distance_ready = 0;
		  if (distance_um > 0 && distance_um <= distance_threshold_um)
		  {
			  trigger_count++;
			  release_count = 0;
			  if (trigger_count >= DEBOUNCE_COUNT)
			  {
				  system_state = 'R';
				  trigger_count = 0;
				  SPI1_Link_SetCommand(SPI_LINK_CMD_START);
				  AudioFilter_Reset();
			  }
		  }
		  else
		  {
			  trigger_count = 0;
		  }
	  }
	  else if (system_state == 'R' && distance_ready)
	  {
		  distance_ready = 0;
		  if (distance_um > distance_threshold_um)
		  {
			  release_count++;
			  trigger_count = 0;
			  if (release_count >= DEBOUNCE_COUNT)
			  {
				  system_state = 'D';
				  release_count = 0;
				  SPI1_Link_SetCommand(SPI_LINK_CMD_STOP);
				  AudioFilter_Reset();
			  }
		  }
		  else
		  {
			  release_count = 0;
		  }
	  }
	  else if (distance_ready)
	  {
		  distance_ready = 0;  // Clear flag in other modes
	  }
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
  hspi1.Init.Direction = SPI_DIRECTION_2LINES;
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
  sConfigIC.ICPolarity = TIM_INPUTCHANNELPOLARITY_BOTHEDGE;
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
  htim15.Init.Period = 500-1;
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
  huart1.Init.BaudRate = 230400;
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

// --- Timer Callbacks ---

void HAL_TIM_PeriodElapsedCallback(TIM_HandleTypeDef* htim)
{
	if (htim == &htim15)
	{
		// Trigger HC-SR04 read every 500ms
		if (system_state == 'D' || system_state == 'T' || system_state == 'R')
		{
			HCSR04_Read();
		}
	}
}

void HAL_TIM_IC_CaptureCallback(TIM_HandleTypeDef *htim)
{
	if (htim->Channel == HAL_TIM_ACTIVE_CHANNEL_1)
	{
		if (system_state != 'T' && system_state != 'D' && system_state != 'R')
		{
			Is_First_Captured = 0;
			return;
		}

		if (Is_First_Captured == 0)
		{
			IC_Val1 = HAL_TIM_ReadCapturedValue(htim, TIM_CHANNEL_1);
			Is_First_Captured = 1;
		}
		else
		{
			IC_Val2 = HAL_TIM_ReadCapturedValue(htim, TIM_CHANNEL_1);

			if (IC_Val2 > IC_Val1)
				Difference = IC_Val2 - IC_Val1;
			else
				Difference = (0xFFFFFFFF - IC_Val1) + IC_Val2 + 1;

			// distance_um = Difference_us * 343 / 20 (integer, no float)
			// TIM2 @ 1MHz, so Difference = time in microseconds
			distance_um = (Difference * 343) / 20;
			Is_First_Captured = 0;
			distance_ready = 1;
		}
	}
}

// --- SPI and UART Callbacks ---

void SPI1_IRQHandler(void)
{
	uint32_t sr = SPI1->SR;

	if ((sr & SPI_SR_RXNE) != 0U)
	{
		uint16_t sample = *((__IO uint16_t *)&SPI1->DR);

		if ((SPI1->SR & SPI_SR_TXE) != 0U)
		{
			*((__IO uint16_t *)&SPI1->DR) = spi_tx_command;
		}

		spi_rx_sample_count++;
		if (system_state == 'M' || system_state == 'R')
		{
			AudioFilter_ProcessSample(sample);
		}
	}

	if ((SPI1->SR & SPI_SR_OVR) != 0U)
	{
		volatile uint16_t clear_dr = *((__IO uint16_t *)&SPI1->DR);
		volatile uint32_t clear_sr = SPI1->SR;
		(void)clear_dr;
		(void)clear_sr;
		spi_overrun_count++;
	}
}

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
	if (huart->Instance == USART2)
	{
		// Command from PC
		if (pc_pending_threshold_byte)
		{
			if (pc_rx_byte > 0U)
			{
				distance_threshold_um = ((uint32_t)pc_rx_byte) * 10000U;
			}
			pc_pending_threshold_byte = 0;
		}
		else if (pc_rx_byte == 'C')
		{
			pc_pending_threshold_byte = 1;
		}
		else if (pc_rx_byte == 'M')
		{
			system_state = 'M';
			HAL_TIM_Base_Stop_IT(&htim15);
			AudioFilter_Reset();
			SPI1_Link_SetCommand(SPI_LINK_CMD_START);
		}
		else if (pc_rx_byte == 'S')
		{
			system_state = 'S';
			HAL_TIM_Base_Stop_IT(&htim15);
			AudioFilter_Reset();
			SPI1_Link_SetCommand(SPI_LINK_CMD_STOP);
		}
		else if (pc_rx_byte == 'D')
		{
			// Distance Trigger Mode is handled locally; SPI carries start/stop to Sampling STM.
			system_state = 'D';
			AudioFilter_Reset();
			SPI1_Link_SetCommand(SPI_LINK_CMD_STOP);
			HAL_TIM_Base_Start_IT(&htim15);
		}
		else if (pc_rx_byte == 'T')
		{
			// Distance Test Mode is handled locally.
			system_state = 'T';
			SPI1_Link_SetCommand(SPI_LINK_CMD_STOP);
			HAL_TIM_Base_Start_IT(&htim15);
		}

		HAL_UART_Receive_IT(&huart2, &pc_rx_byte, 1);
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
