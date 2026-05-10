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

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
TIM_HandleTypeDef htim2;
TIM_HandleTypeDef htim15;

UART_HandleTypeDef huart1;
UART_HandleTypeDef huart2;

/* USER CODE BEGIN PV */
uint8_t rx_byte;          // Byte received from Sampling STM (USART1)
uint8_t pc_rx_byte;       // Byte received from PC (USART2)

// HC-SR04 sensor
TIM_HandleTypeDef htim2;
TIM_HandleTypeDef htim15;
volatile uint32_t IC_Val1 = 0;
volatile uint32_t IC_Val2 = 0;
volatile uint32_t Difference = 0;
volatile uint8_t Is_First_Captured = 0;
volatile uint32_t distance_um = 0;
volatile uint8_t distance_ready = 0;

// System state: 'S'=stop, 'M'=manual, 'D'=distance wait, 'R'=recording, 'T'=test
volatile uint8_t system_state = 'S';

// Distance trigger config
#define DISTANCE_TRIGGER_DEFAULT_CM 10U
#define DISTANCE_TRIGGER_MIN_CM 2U
#define DISTANCE_TRIGGER_MAX_CM 200U
#define DISTANCE_CM_TO_UM 10000U
#define DEBOUNCE_COUNT 3  // Require 3 consecutive readings to trigger/stop
uint8_t distance_threshold_cm = DISTANCE_TRIGGER_DEFAULT_CM;
uint32_t distance_threshold_um = DISTANCE_TRIGGER_DEFAULT_CM * DISTANCE_CM_TO_UM;
uint8_t expecting_distance_threshold = 0;
uint8_t trigger_count = 0;  // Consecutive in-range readings
uint8_t release_count = 0;  // Consecutive out-of-range readings
/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_USART2_UART_Init(void);
static void MX_USART1_UART_Init(void);
static void MX_TIM15_Init(void);
static void MX_TIM2_Init(void);
/* USER CODE BEGIN PFP */
void HCSR04_Read(void);
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
	HAL_GPIO_WritePin(GPIOB, GPIO_PIN_5, GPIO_PIN_SET);
	for (volatile int i = 0; i < 300; i++) {}  // ~10us delay at 32MHz
	HAL_GPIO_WritePin(GPIOB, GPIO_PIN_5, GPIO_PIN_RESET);
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
  MX_USART2_UART_Init();
  MX_USART1_UART_Init();
  MX_TIM15_Init();
  MX_TIM2_Init();
  /* USER CODE BEGIN 2 */

  // Configure PB5 as GPIO output for HC-SR04 trigger
  {
	  GPIO_InitTypeDef GPIO_InitStruct = {0};
	  __HAL_RCC_GPIOB_CLK_ENABLE();
	  GPIO_InitStruct.Pin = GPIO_PIN_5;
	  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
	  GPIO_InitStruct.Pull = GPIO_NOPULL;
	  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
	  HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);
	  HAL_GPIO_WritePin(GPIOB, GPIO_PIN_5, GPIO_PIN_RESET);
  }

  // Init timers for HC-SR04
  HAL_TIM_IC_Start_IT(&htim2, TIM_CHANNEL_1);

  // Start UART receive on both ports
  HAL_UART_Receive_IT(&huart1, &rx_byte, 1);
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
				  uint8_t cmd = 'M';
				  HAL_UART_Transmit(&huart1, &cmd, 1, 10);
				  uart_send_str(&huart2, "REC_START\r\n");
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
				  uint8_t cmd = 'S';
				  HAL_UART_Transmit(&huart1, &cmd, 1, 10);
				  uart_send_str(&huart2, "REC_STOP\r\n");
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
  huart2.Init.BaudRate = 230400;
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
  HAL_GPIO_WritePin(GPIOB, LD3_Pin|HCSR04_TRIG_Pin, GPIO_PIN_RESET);

  /*Configure GPIO pins : LD3_Pin HCSR04_TRIG_Pin */
  GPIO_InitStruct.Pin = LD3_Pin|HCSR04_TRIG_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);

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

// --- UART Callbacks ---

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
	if (huart->Instance == USART1)
	{
		// Data from Sampling STM32 (ADC bytes)
		// Apply 3-sample moving average only during recording modes
		if (system_state == 'M' || system_state == 'R')
		{
			static uint8_t buffer[3] = {0, 0, 0};
			static uint8_t index = 0;

			buffer[index] = rx_byte;
			index = (index + 1) % 3;

			uint16_t sum = buffer[0] + buffer[1] + buffer[2];
			uint8_t average = (uint8_t)(sum / 3);

			HAL_UART_Transmit_IT(&huart2, &average, 1);
		}

		HAL_UART_Receive_IT(&huart1, &rx_byte, 1);
	}
	else if (huart->Instance == USART2)
	{
		// Command from PC
		if (expecting_distance_threshold != 0U)
		{
			if (pc_rx_byte < DISTANCE_TRIGGER_MIN_CM)
			{
				distance_threshold_cm = DISTANCE_TRIGGER_MIN_CM;
			}
			else if (pc_rx_byte > DISTANCE_TRIGGER_MAX_CM)
			{
				distance_threshold_cm = DISTANCE_TRIGGER_MAX_CM;
			}
			else
			{
				distance_threshold_cm = pc_rx_byte;
			}

			distance_threshold_um = (uint32_t)distance_threshold_cm * DISTANCE_CM_TO_UM;
			trigger_count = 0;
			release_count = 0;
			expecting_distance_threshold = 0U;

			char tmp[12];
			uart_send_str(&huart2, "ACK:R:");
			uart_send_str(&huart2, u32_to_str(distance_threshold_cm, tmp, sizeof(tmp)));
			uart_send_str(&huart2, "\r\n");
		}
		else if (pc_rx_byte == 'M')
		{
			system_state = 'M';
			HAL_TIM_Base_Stop_IT(&htim15);
			// Forward 'M' to Sampling STM to start ADC
			HAL_UART_Transmit_IT(&huart1, &pc_rx_byte, 1);
		}
		else if (pc_rx_byte == 'S')
		{
			system_state = 'S';
			HAL_TIM_Base_Stop_IT(&htim15);
			// Forward 'S' to Sampling STM to stop ADC
			HAL_UART_Transmit_IT(&huart1, &pc_rx_byte, 1);
		}
		else if (pc_rx_byte == 'D')
		{
			// Distance Trigger Mode - handled locally, don't forward
			system_state = 'D';
			HAL_TIM_Base_Start_IT(&htim15);
		}
		else if (pc_rx_byte == 'T')
		{
			// Distance Test Mode - handled locally, don't forward
			system_state = 'T';
			HAL_TIM_Base_Start_IT(&htim15);
		}
		else if (pc_rx_byte == 'R')
		{
			// Range configuration command: next byte is distance in cm
			expecting_distance_threshold = 1U;
		}

		HAL_GPIO_TogglePin(LD3_GPIO_Port, LD3_Pin);
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
