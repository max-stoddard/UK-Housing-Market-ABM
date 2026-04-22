package housing;

import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.List;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ConfigLoadingCompatibilityTest {

    private static final Path REPO_ROOT = Paths.get("").toAbsolutePath();

    @Test
    void liveResourcesConfigLoadsBackfilledBTLFields() {
        Config config = loadConfig("src/main/resources/config.properties");

        assertBackfilledBTLDefaults(config);
    }

    @Test
    void v410SnapshotConfigLoadsBackfilledBTLFields() {
        Config config = loadConfig("input-data-versions/v4.10/config.properties");

        assertBackfilledBTLDefaults(config);
    }

    @Test
    void historicalSnapshotConfigLoadsBackfilledBTLFields() {
        Config config = loadConfig("input-data-versions/v0/config.properties");

        assertBackfilledBTLDefaults(config);
    }

    @Test
    void everyCheckedInSnapshotConfigLoadsBackfilledBTLFields() throws IOException {
        List<Path> snapshotConfigs = Files.list(REPO_ROOT.resolve("input-data-versions"))
                .filter(Files::isDirectory)
                .filter(path -> path.getFileName().toString().startsWith("v"))
                .map(path -> path.resolve("config.properties"))
                .filter(Files::exists)
                .sorted()
                .collect(Collectors.toList());

        assertTrue(snapshotConfigs.size() >= 20, "Expected the checked-in versioned snapshots to be present");

        for (Path configPath : snapshotConfigs) {
            assertBackfilledBTLDefaults(new Config(configPath.toString()));
        }
    }

    private static Config loadConfig(String relativePath) {
        return new Config(REPO_ROOT.resolve(relativePath).toString());
    }

    private static void assertBackfilledBTLDefaults(Config config) {
        assertAll(
                () -> assertFalse(config.enableBTLAmortizingMortgageMode),
                () -> assertFalse(config.enableBTLDownpaymentLognormal),
                () -> assertFalse(config.enableBTLAlternativeReturn),
                () -> assertEquals(config.DOWNPAYMENT_OO_SCALE, config.DOWNPAYMENT_BTL_SCALE, 1.0e-12),
                () -> assertEquals(config.DOWNPAYMENT_OO_SHAPE, config.DOWNPAYMENT_BTL_SHAPE, 1.0e-12),
                () -> assertEquals(0.0, config.BTL_ALTERNATIVE_RETURN, 1.0e-12)
        );
    }
}
