package housing;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ModelObservabilityRegressionTest {

    private static final Path REPO_ROOT = Paths.get("").toAbsolutePath();
    private static final List<String> APPENDED_OUTPUT_COLUMNS = Arrays.asList(
            "nonHousingConsumption",
            "rentalCashOutflow",
            "downpaymentCashOutflow",
            "mortgagePrincipalPayment",
            "mortgageInterestPayment",
            "totalFinancialWealth",
            "totalHousingNetWealth",
            "totalHousingGrossWealth"
    );

    @TempDir
    Path tempDir;

    @Test
    void preservesLegacyOutputPrefixAndLeavesNewMicroFilesOptIn() throws Exception {
        Path outputDir = tempDir.resolve("results");
        Path configPath = writeCurrentTinyConfig(tempDir.resolve("current-baseline.properties"));

        ProcessResult result = runModel(configPath, outputDir);
        assertEquals(0, result.exitCode, () -> "STDOUT:\n" + result.stdout + "\nSTDERR:\n" + result.stderr);

        List<String> baselineLines = Files.readAllLines(resourcePath("t7t9/master-baseline/Output-run1.csv"));
        List<String> currentLines = Files.readAllLines(outputDir.resolve("Output-run1.csv"));
        assertEquals(baselineLines.size(), currentLines.size());

        List<String> baselineHeaderTokens = splitSemicolonRow(baselineLines.get(0));
        List<String> currentHeaderTokens = splitSemicolonRow(currentLines.get(0));

        assertAll(
                () -> assertEquals(baselineHeaderTokens,
                        currentHeaderTokens.subList(0, baselineHeaderTokens.size())),
                () -> assertEquals(APPENDED_OUTPUT_COLUMNS,
                        currentHeaderTokens.subList(baselineHeaderTokens.size(), currentHeaderTokens.size()))
        );

        for (int lineIndex = 1; lineIndex < baselineLines.size(); lineIndex += 1) {
            List<String> baselineTokens = splitSemicolonRow(baselineLines.get(lineIndex));
            List<String> currentTokens = splitSemicolonRow(currentLines.get(lineIndex));
            assertEquals(baselineTokens, currentTokens.subList(0, baselineTokens.size()),
                    "Legacy output prefix changed on line " + lineIndex);
            assertEquals(baselineTokens.size() + APPENDED_OUTPUT_COLUMNS.size(), currentTokens.size(),
                    "Unexpected output width on line " + lineIndex);
        }

        assertAll(
                () -> assertEquals(
                        Files.readString(resourcePath("t7t9/master-baseline/HousingWealth-run1.csv"), StandardCharsets.UTF_8),
                        Files.readString(outputDir.resolve("HousingWealth-run1.csv"), StandardCharsets.UTF_8)
                ),
                () -> assertFalse(Files.exists(outputDir.resolve("TotalDebt-run1.csv"))),
                () -> assertFalse(Files.exists(outputDir.resolve("HousingStatus-run1.csv"))),
                () -> assertFalse(Files.exists(outputDir.resolve("NonHousingConsumption-run1.csv")))
        );
    }

    private static Path writeCurrentTinyConfig(Path outputPath) throws IOException {
        String configText = Files.readString(REPO_ROOT.resolve("src/main/resources/config.properties"), StandardCharsets.UTF_8);
        configText = replaceSetting(configText, "N_STEPS", "996");
        configText = replaceSetting(configText, "TARGET_POPULATION", "100");
        configText = replaceSetting(configText, "TIME_TO_START_RECORDING_TRANSACTIONS", "996");
        configText = replaceSetting(configText, "recordTransactions", "false");
        configText = replaceSetting(configText, "recordNBidUpFrequency", "false");
        configText = replaceSetting(configText, "recordCoreIndicators", "false");
        configText = replaceSetting(configText, "recordQualityBandPrice", "false");
        configText = replaceSetting(configText, "recordHouseholdID", "false");
        configText = replaceSetting(configText, "recordEmploymentIncome", "false");
        configText = replaceSetting(configText, "recordRentalIncome", "false");
        configText = replaceSetting(configText, "recordBankBalance", "false");
        configText = replaceSetting(configText, "recordHousingWealth", "true");
        configText = replaceSetting(configText, "recordTotalDebt", "false");
        configText = replaceSetting(configText, "recordHousingStatus", "false");
        configText = replaceSetting(configText, "recordConsumption", "false");
        configText = replaceSetting(configText, "recordNHousesOwned", "false");
        configText = replaceSetting(configText, "recordAge", "false");
        configText = replaceSetting(configText, "recordSavingRate", "false");
        Files.writeString(outputPath, configText, StandardCharsets.UTF_8);
        return outputPath;
    }

    private static String replaceSetting(String text, String key, String value) {
        Pattern pattern = Pattern.compile("(?m)^" + Pattern.quote(key) + " = .*?$");
        Matcher matcher = pattern.matcher(text);
        assertTrue(matcher.find(), "Missing config key: " + key);
        return matcher.replaceFirst(Matcher.quoteReplacement(key + " = " + value));
    }

    private static ProcessResult runModel(Path configPath, Path outputDir) throws Exception {
        Files.createDirectories(outputDir);
        ProcessBuilder processBuilder = new ProcessBuilder(
                Path.of(System.getProperty("java.home"), "bin", "java").toString(),
                "-cp",
                System.getProperty("java.class.path"),
                "housing.Model",
                "-configFile",
                configPath.toAbsolutePath().toString(),
                "-outputFolder",
                outputDir.toAbsolutePath().toString() + "/",
                "-dev"
        );
        processBuilder.directory(REPO_ROOT.toFile());
        Process process = processBuilder.start();
        String stdout = readStream(process.getInputStream());
        String stderr = readStream(process.getErrorStream());
        int exitCode = process.waitFor();
        return new ProcessResult(exitCode, stdout, stderr);
    }

    private static String readStream(InputStream stream) throws IOException {
        ByteArrayOutputStream outputStream = new ByteArrayOutputStream();
        byte[] buffer = new byte[4096];
        int read;
        while ((read = stream.read(buffer)) != -1) {
            outputStream.write(buffer, 0, read);
        }
        return outputStream.toString(StandardCharsets.UTF_8.name());
    }

    private static List<String> splitSemicolonRow(String line) {
        return Arrays.stream(line.split(";"))
                .map(String::trim)
                .collect(Collectors.toList());
    }

    private static Path resourcePath(String resourceName) throws Exception {
        return Paths.get(Objects.requireNonNull(
                ModelObservabilityRegressionTest.class.getClassLoader().getResource(resourceName)).toURI());
    }

    private static final class ProcessResult {
        private final int exitCode;
        private final String stdout;
        private final String stderr;

        private ProcessResult(int exitCode, String stdout, String stderr) {
            this.exitCode = exitCode;
            this.stdout = stdout;
            this.stderr = stderr;
        }
    }
}
